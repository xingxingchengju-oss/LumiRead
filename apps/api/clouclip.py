"""Parent-only, session-bound playback of the original Clouclip observation clock."""

import bisect
import json
import time
from datetime import datetime
from functools import cache
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from . import storage

SCHEMA = """
CREATE TABLE IF NOT EXISTS clouclip_playbacks(
    sid TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    segment TEXT NOT NULL CHECK(segment IN ('stable','near','dim')),
    status TEXT NOT NULL DEFAULT 'ready' CHECK(status IN ('ready','playing','paused','finished')),
    speed INTEGER NOT NULL DEFAULT 1 CHECK(speed IN (1,4,10)),
    position REAL NOT NULL DEFAULT 0, anchor REAL,
    processed INTEGER NOT NULL DEFAULT 0, generation INTEGER NOT NULL DEFAULT 0,
    scene TEXT NOT NULL DEFAULT 'paper'
);
CREATE TABLE IF NOT EXISTS clouclip_events(
    sid TEXT NOT NULL REFERENCES clouclip_playbacks(sid) ON DELETE CASCADE,
    metric TEXT NOT NULL, start_line INTEGER NOT NULL, started_at TEXT NOT NULL,
    end_line INTEGER, ended_at TEXT, PRIMARY KEY(sid,metric,start_line)
);
"""
SegmentId = Literal["stable", "near", "dim"]
Speed = Literal[1, 4, 10]
Metric = Literal["Dis", "Lux"]
Scene = Literal["paper", "phone", "computer"]
DISTANCES = {"paper": 33, "phone": 40, "computer": 50}
RULE_VERSION = "clouclip-duration-v2"


class Record(BaseModel):
    line: int
    Date: str
    Dis: int | None
    Lux: int | None
    distance_cm: int | None
    illuminance_lx: int | None
    offset_seconds: int


class Episode(BaseModel):
    metric: Metric
    start_line: int
    started_at: str
    end_line: int | None = None
    ended_at: str | None = None
    source: str = "Clouclip"
    scene: Scene = "paper"
    scene_source: str = "manual_scenario"
    rule_version: str = RULE_VERSION


class Source(BaseModel):
    dataset: str
    commit: str
    sha256: str
    file_url: str
    supplement: str
    article: str
    timezone: str


class Excerpt(BaseModel):
    id: SegmentId
    title: str
    first_line: int
    last_line: int
    sha256: str
    starts_at: str
    ends_at: str
    duration_seconds: int
    total_samples: int


class Playback(BaseModel):
    segment: Excerpt
    source: Source
    status: Literal["ready", "playing", "paused", "finished"]
    speed: Speed
    generation: int
    position_seconds: float
    records: list[Record]
    events: list[Episode]
    scene: Scene
    distance_limit_cm: int


class Control(BaseModel):
    action: Literal["play", "pause", "replay", "speed", "scene"]
    speed: Speed | None = None
    scene: Scene | None = None
    generation: int = Field(ge=0)

    @model_validator(mode="after")
    def valid_speed(self):
        if (self.action == "speed") != (self.speed is not None):
            raise ValueError("Choose a speed only when changing replay speed.")
        if (self.action == "scene") != (self.scene is not None):
            raise ValueError("Choose a scene only when changing the rule scenario.")
        return self


def normalized(row, first_time):
    dis, lux = row["Dis"], row["Lux"]
    sleeping = dis == -1 or lux == -1
    return Record(
        **row,
        distance_cm=dis
        if not sleeping and dis is not None and 0 < dis <= 120
        else None,
        illuminance_lx=lux if not sleeping and lux is not None and lux >= 0 else None,
        offset_seconds=int(
            (datetime.fromisoformat(row["Date"]) - first_time).total_seconds()
        ),
    )


@cache
def dataset():
    manifest = json.loads((storage.ROOT / "data/clouclip/segments.json").read_text())
    result = {}
    for key, part in manifest["segments"].items():
        first_time = datetime.fromisoformat(part["records"][0]["Date"])
        points = [normalized(row, first_time) for row in part["records"]]
        result[key] = (
            Excerpt(
                id=key,
                **{k: part[k] for k in ("title", "first_line", "last_line", "sha256")},
                starts_at=points[0].Date,
                ends_at=points[-1].Date,
                duration_seconds=points[-1].offset_seconds,
                total_samples=len(points),
            ),
            points,
        )
    return Source(**manifest["source"]), result


def evaluate(points, scene: Scene = "paper"):
    """Pure prefix evaluation. Missing data clears streaks and never proves recovery."""
    events = []
    distance = DISTANCES[scene]
    for metric, low, recovered, seconds in (
        ("Dis", distance, distance + 2, 10),
        ("Lux", 300, 350, 30),
    ):
        episode = None
        first_low = None
        recovery_points = 0
        previous = None
        for point in points:
            if previous is not None and not 0 < point.offset_seconds - previous <= 5:
                first_low, recovery_points = None, 0
            previous = point.offset_seconds
            value = point.distance_cm if metric == "Dis" else point.illuminance_lx
            if value is None:
                first_low, recovery_points = None, 0
                continue
            if episode is None:
                if value >= low:
                    first_low = None
                    continue
                if first_low is None:
                    first_low = point.offset_seconds
                if point.offset_seconds - first_low >= seconds:
                    episode = Episode(
                        metric=metric,
                        start_line=point.line,
                        started_at=point.Date,
                        scene=scene,
                    )
                    events.append(episode)
                    first_low = None
            else:
                recovery_points = recovery_points + 1 if value >= recovered else 0
                if recovery_points == 2:
                    episode.end_line, episode.ended_at = point.line, point.Date
                    episode = None
                    recovery_points = 0
    return sorted(events, key=lambda e: (e.start_line, e.metric))


def initialize():
    db = storage.connect()
    try:
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        if "scene" not in {
            r["name"] for r in db.execute("PRAGMA table_info(clouclip_playbacks)")
        }:
            db.execute(
                "ALTER TABLE clouclip_playbacks ADD COLUMN scene TEXT NOT NULL DEFAULT 'paper'"
            )
            db.execute("DELETE FROM clouclip_events")
            for row in db.execute("SELECT * FROM clouclip_playbacks"):
                points = dataset()[1][row["segment"]][1]
                save_events(db, row["sid"], evaluate(points[: row["processed"]]))
        db.commit()
    finally:
        db.close()


def bind(db, sid, segment):
    if segment not in dataset()[1]:
        raise ValueError("Unknown Clouclip excerpt")
    db.execute(
        "INSERT INTO clouclip_playbacks(sid,segment) VALUES(?,?) ON CONFLICT(sid) DO NOTHING",
        (sid, segment),
    )
    if playback_row(db, sid)["segment"] != segment:
        raise ValueError("A session is already bound to a different excerpt")


def playback_row(db, sid):
    row = db.execute("SELECT * FROM clouclip_playbacks WHERE sid=?", (sid,)).fetchone()
    if row is None:
        raise HTTPException(404, "此场次未配对公开传感器片段。")
    return row


def save_events(db, sid, events):
    db.executemany(
        """INSERT INTO clouclip_events(sid,metric,start_line,started_at,end_line,ended_at)
        VALUES(?,?,?,?,?,?) ON CONFLICT(sid,metric,start_line) DO UPDATE SET
        end_line=excluded.end_line, ended_at=excluded.ended_at""",
        [
            (sid, e.metric, e.start_line, e.started_at, e.end_line, e.ended_at)
            for e in events
        ],
    )


def advance(db, row, now):
    if row["status"] != "playing":
        return row["position"]
    excerpt, points = dataset()[1][row["segment"]]
    sid = row["sid"]
    position = min(
        excerpt.duration_seconds,
        row["position"] + max(0, now - row["anchor"]) * row["speed"],
    )
    count = bisect.bisect_right(points, position, key=lambda p: p.offset_seconds)
    if count > row["processed"]:
        save_events(db, sid, evaluate(points[:count], row["scene"]))
        db.execute(
            "UPDATE clouclip_playbacks SET processed=? WHERE sid=?", (count, sid)
        )
    if count == len(points):
        db.execute(
            "UPDATE clouclip_playbacks SET status='finished', position=?, anchor=NULL WHERE sid=?",
            (excerpt.duration_seconds, sid),
        )
    return position


def advance_all():
    # Avoid a write lock while the majority of lecture sessions are idle.
    with storage.transaction() as db:
        playing = [
            r[0]
            for r in db.execute(
                "SELECT sid FROM clouclip_playbacks WHERE status='playing'"
            )
        ]
    for sid in playing:
        with storage.transaction(True) as db:
            row = db.execute(
                "SELECT * FROM clouclip_playbacks WHERE sid=?", (sid,)
            ).fetchone()
            if row is not None:
                advance(db, row, time.time())


def state(db, sid, now):
    position = advance(db, playback_row(db, sid), now)
    row = playback_row(db, sid)
    source, segments = dataset()
    excerpt, points = segments[row["segment"]]
    events = db.execute(
        "SELECT metric,start_line,started_at,end_line,ended_at FROM clouclip_events "
        "WHERE sid=? ORDER BY start_line,metric",
        (sid,),
    )
    return Playback(
        source=source,
        segment=excerpt,
        status=row["status"],
        speed=row["speed"],
        generation=row["generation"],
        position_seconds=position,
        records=points[: row["processed"]],
        events=[Episode(**e, scene=row["scene"]) for e in events],
        scene=row["scene"],
        distance_limit_cm=DISTANCES[row["scene"]],
    )


def control(db, sid, action, now):
    position = advance(db, playback_row(db, sid), now)
    row = playback_row(db, sid)
    # Ignore a duplicate replay or a stale command sent before the last reset.
    if action.generation != row["generation"]:
        return state(db, sid, now)
    if action.action == "scene" and action.scene != row["scene"]:
        db.execute("DELETE FROM clouclip_events WHERE sid=?", (sid,))
        db.execute(
            """UPDATE clouclip_playbacks SET scene=?, status='ready', position=0,
                   anchor=NULL, processed=0, generation=generation+1 WHERE sid=?""",
            (action.scene, sid),
        )
    elif action.action == "replay":
        db.execute("DELETE FROM clouclip_events WHERE sid=?", (sid,))
        db.execute(
            "UPDATE clouclip_playbacks SET status='playing', position=0, anchor=?, "
            "processed=0, generation=generation+1 WHERE sid=?",
            (now, sid),
        )
    elif action.action == "play" and row["status"] in ("ready", "paused"):
        db.execute(
            "UPDATE clouclip_playbacks SET status='playing', anchor=? WHERE sid=?",
            (now, sid),
        )
    elif action.action == "pause" and row["status"] == "playing":
        db.execute(
            "UPDATE clouclip_playbacks SET status='paused', position=?, anchor=NULL WHERE sid=?",
            (position, sid),
        )
    elif action.action == "speed":
        anchor = now if row["status"] == "playing" else None
        db.execute(
            "UPDATE clouclip_playbacks SET position=?,anchor=?,speed=? WHERE sid=?",
            (position, anchor, action.speed, sid),
        )
    return state(db, sid, now)


def make_router(member):
    router = APIRouter(prefix="/sessions/{sid}/clouclip", tags=["Clouclip"])

    @router.get("", response_model=Playback)
    def read(sid: str, request: Request):
        with storage.transaction(True) as db:
            member(db, request, sid, ("parent",))
            return state(db, sid, time.time())

    @router.post("/control", response_model=Playback)
    def update(sid: str, body: Control, request: Request):
        with storage.transaction(True) as db:
            member(db, request, sid, ("parent",))
            return control(db, sid, body, time.time())

    return router
