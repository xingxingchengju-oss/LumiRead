"""Source-clock eye-care rules and public, independently attributable research reports."""

import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta
from functools import cache
from itertools import pairwise
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from typing_extensions import TypedDict

from . import clouclip as cc
from . import storage
from .monitor import Monitor
from .weekly import WeeklyReport, weekly_report

router = APIRouter(prefix="/eye-care", tags=["Eye care"])
RULE = "reading-rest-v1"
Study = Literal["paper", "writing", "electronic", "other"]
ClockSource = Literal["manual", "rule_demo", "RitW", "simulated"]
ReportSource = Literal["ritw", "clouclip", "simulated"]
RITW = storage.ROOT / "artifacts/ritw"


@router.get("/weekly-report", response_model=WeeklyReport)
def parent_weekly_report():
    return weekly_report()


class Span(BaseModel):
    state: Literal["active", "away", "rest", "unknown", "end"]
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(ge=0, allow_inf_nan=False)
    scene: Study | None = None


class Clock(BaseModel):
    scene: Study
    source: ClockSource
    start_second: float = Field(default=0, ge=0, allow_inf_nan=False)
    spans: list[Span] = Field(max_length=10000)

    @model_validator(mode="after")
    def ordered(self):
        previous = self.start_second
        for span in self.spans:
            if span.start < previous or span.end < span.start:
                raise ValueError("Intervals must be ordered and disjoint.")
            if span.state == "end" and span.start != span.end:
                raise ValueError("End is a point on the source clock.")
            previous = span.end
            if span.scene is not None and self.source != "RitW":
                raise ValueError("A manual session uses its selected scene throughout.")
        return self


class ClockEvent(TypedDict):
    kind: Literal["rest_due", "rest_completed"]
    source: ClockSource
    source_second: float
    scene: Study
    scene_source: Literal["model", "manual_scenario", "simulated"]
    rule_version: str


class ClockResult(TypedDict):
    source: ClockSource
    rule_version: str
    active_seconds: float
    bout_seconds: float
    missing_seconds: float
    break_seconds: float
    threshold_seconds: int
    events: list[ClockEvent]


@router.post("/clock", response_model=ClockResult)
def clock(body: Clock):
    scene = body.scene
    last = body.start_second
    total = bout = electronic = rest = missing = inactive = 0
    notified = completed = False
    events = []

    def event(kind, at):
        events.append(
            {
                "kind": kind,
                "source": body.source,
                "source_second": at,
                "scene": scene,
                "scene_source": {"RitW": "model", "simulated": "simulated"}.get(
                    body.source, "manual_scenario"
                ),
                "rule_version": RULE,
            }
        )

    for span in body.spans:
        if span.start > last:
            gap = span.start - last
            missing += gap
            inactive += gap
            rest = 0
            completed = False
        duration = span.end - span.start
        last = span.end
        if span.state != "rest":
            rest = 0
            completed = False
        if span.state == "active":
            if inactive >= 600:
                bout, electronic, notified = 0, 0, False
            inactive = 0
            scene = span.scene or body.scene
            wait = 2400 - bout
            if scene == "electronic":
                wait = min(wait, 1800 - electronic)
                electronic += duration
            else:
                electronic = 0
            if not notified and 0 < wait <= duration:
                event("rest_due", span.start + wait)
                notified = True
            total += duration
            bout += duration
        elif span.state == "rest":
            inactive += duration
            if not completed and rest < 600 <= rest + duration:
                event("rest_completed", span.start + 600 - rest)
                bout, electronic, notified, completed = 0, 0, False, True
            rest += duration
        elif span.state in ("unknown", "away"):
            inactive += duration
            if span.state == "unknown":
                missing += duration
        elif span.state == "end":
            bout, electronic, inactive, notified = 0, 0, 0, False
        if inactive >= 600:
            bout, electronic, notified = 0, 0, False
    return {
        "source": body.source,
        "rule_version": RULE,
        "active_seconds": total,
        "bout_seconds": bout,
        "missing_seconds": missing,
        "break_seconds": rest,
        "threshold_seconds": 1800 if scene == "electronic" else 2400,
        "events": events,
    }


def predicted_clock(clip):
    start, end = clip["evaluation"]
    spans = [
        Span(
            state="active" if reading else "away",
            start=a,
            end=b,
            scene=("other", "paper", "electronic", "other")[medium]
            if reading
            else None,
        )
        for a, b, reading, medium in clip["intervals"]
    ]
    last = spans[-1].end if spans else start
    if last < end:
        spans.append(Span(state="unknown", start=last, end=end))
    return clock(Clock(scene="other", source="RitW", start_second=start, spans=spans))


@cache
def research():
    data = json.loads((RITW / "replays.json").read_text())
    for clip in data["clips"]:
        clip["clock"] = predicted_clock(clip)
    return data


class ModelScore(TypedDict):
    read_f1: float
    read_precision: float
    read_recall: float
    medium_recall: dict[str, float]
    medium_support: dict[str, int]
    duration_mae_seconds: float
    hard_negative_windows: int
    hard_false_positive_windows: int
    hard_false_positive_rate: float


class ScoredClip(TypedDict):
    id: str
    date: str
    group: str
    evaluation: tuple[float, float]
    reference_intervals: list[tuple[float, float]]
    reference_medium: int
    covered_seconds: int
    predicted_read_seconds: int
    reference_read_seconds: float
    intervals: list[tuple[int, int, int, int]]
    baseline_intervals: list[tuple[int, int, int, int]]
    clock: ClockResult


class PanelMetrics(TypedDict):
    revision: str
    splits: dict[str, dict[str, int]]
    official: ModelScore
    logistic: ModelScore


class Research(TypedDict):
    showcase: str
    classes: list[str]
    clips: list[ScoredClip]
    metrics: PanelMetrics


@router.get("/research", response_model=Research)
def research_view():
    return {**research(), "metrics": json.loads((RITW / "metrics.json").read_text())}


@router.get("/monitor", response_model=Monitor)
@cache
def monitor_view():
    file = RITW / "monitor.json"
    if not file.is_file():
        raise HTTPException(503, "本机尚未准备双样片回放数据。")
    return json.loads(file.read_text())


@router.get(
    "/preview/{recording}",
    response_class=FileResponse,
    responses={200: {"content": {"video/mp4": {}}}},
)
def preview(recording: str):
    legacy = recording == research()["showcase"]
    if not legacy and (
        not (RITW / "monitor.json").is_file()
        or recording not in {c["id"] for c in monitor_view()["clips"]}
    ):
        raise HTTPException(404, "没有对应的演示录像。")
    file = storage.ROOT / ".cache/ritw/sequences" / recording / "preview.mp4"
    if not file.is_file():
        raise HTTPException(404, "此电脑尚未获取该录像，请通过 Meta 数据入口下载。")
    return FileResponse(file, media_type="video/mp4")


class SensorExcerpt(BaseModel):
    segment: cc.Excerpt
    records: list[cc.Record]
    events: list[cc.Episode]
    source: cc.Source
    scene: cc.Scene
    distance_limit_cm: int
    rule_version: str


@router.get("/excerpts/{segment}", response_model=SensorExcerpt)
def excerpt(segment: cc.SegmentId, scene: cc.Scene = "paper"):
    source, excerpts = cc.dataset()
    part, points = excerpts[segment]
    return {
        "segment": part,
        "records": points,
        "events": cc.evaluate(points, scene),
        "source": source,
        "scene": scene,
        "distance_limit_cm": cc.DISTANCES[scene],
        "rule_version": cc.RULE_VERSION,
    }


def blank(day):
    return {
        "date": day,
        "recorded": False,
        "coverage_seconds": 0,
        "distance_seconds": 0,
        "light_seconds": 0,
        "reading_seconds": 0,
        "medium_seconds": Counter(),
        "near": 0,
        "dim": 0,
        "breaks": 0,
        "details": [],
    }


@cache
def measured_days(scene):
    table = {}
    raw = storage.ROOT / "data/clouclip/Sample_Clouclip.csv"
    with raw.open(encoding="utf-8-sig", newline="") as file:
        records = []
        for i, r in enumerate(csv.DictReader(file, delimiter="\t"), 2):
            ts = datetime.fromisoformat(r["Date"])
            if not records:
                first = ts
            records.append(
                cc.normalized(
                    {
                        "line": i,
                        "Date": r["Date"],
                        "Dis": int(r["Dis"]),
                        "Lux": int(r["Lux"]),
                    },
                    first,
                )
            )
    for old, new in pairwise(records):
        day = old.Date[:10]
        if day not in table:
            table[day] = blank(day)
        delta = new.offset_seconds - old.offset_seconds
        if not 0 < delta <= 5:
            continue
        distance = old.distance_cm is not None and new.distance_cm is not None
        light = old.illuminance_lx is not None and new.illuminance_lx is not None
        if not (distance or light):
            continue
        # Split an observed interval at the device's local midnight.
        pieces = [(day, delta)]
        if day != new.Date[:10]:
            next_day = new.Date[:10]
            seconds = int(
                (
                    datetime.fromisoformat(next_day) - datetime.fromisoformat(old.Date)
                ).total_seconds()
            )
            pieces = [(day, seconds), (next_day, delta - seconds)]
        for key, seconds in pieces:
            if seconds <= 0:
                continue
            item = table.setdefault(key, blank(key))
            item["recorded"] = True
            item["coverage_seconds"] += seconds
            item["distance_seconds"] += seconds * distance
            item["light_seconds"] += seconds * light
    for e in cc.evaluate(records, scene):
        item = table[e.started_at[:10]]
        item["near" if e.metric == "Dis" else "dim"] += 1
        item["details"].append(e.model_dump())
    return table


@cache
def reading_days():
    table = {}
    for clip in research()["clips"]:
        day = clip["date"]
        item = table.setdefault(day, blank(day))
        item["recorded"] = True
        item["coverage_seconds"] += clip["covered_seconds"]
        item["reading_seconds"] += int(clip["clock"]["active_seconds"])
        item["breaks"] += sum(e["kind"] == "rest_due" for e in clip["clock"]["events"])
        for start, end, reading, medium in clip["intervals"]:
            if reading:
                item["medium_seconds"][
                    ("Unknown", "Print", "Digital", "Object")[medium]
                ] += end - start
        item["details"].append(
            {
                **{
                    k: clip[k]
                    for k in (
                        "id",
                        "covered_seconds",
                        "predicted_read_seconds",
                        "reference_read_seconds",
                    )
                },
                "events": clip["clock"]["events"],
            }
        )
    return table


@cache
def simulated_days():
    table = {}
    path = storage.ROOT / "data/eyecare/simulated_week.csv"
    with path.open() as file:
        for row in csv.DictReader(file):
            day, scene = row["date"], row["scene"]
            start = datetime.fromisoformat(day + "T" + row["start"])
            duration = int(row["active_minutes"]) * 60
            near_seconds = int(row["near_seconds"])
            dim_seconds = int(row["dim_seconds"])
            limit = cc.DISTANCES[scene]
            points = []
            for t in range(0, duration + 1, 5):
                dis = limit - 4 if near_seconds and t <= near_seconds else limit + 5
                lux = 180 if dim_seconds and 300 <= t <= 300 + dim_seconds else 480
                points.append(
                    cc.normalized(
                        {
                            "line": t // 5 + 1,
                            "Date": str(start + timedelta(seconds=t)),
                            "Dis": dis,
                            "Lux": lux,
                        },
                        start,
                    )
                )
            alerts = cc.evaluate(points, scene)
            activity = clock(
                Clock(
                    scene="paper" if scene == "paper" else "electronic",
                    source="simulated",
                    spans=[Span(state="active", start=0, end=duration)],
                )
            )
            item = table.setdefault(day, blank(day))
            item["recorded"] = True
            item["coverage_seconds"] += duration
            item["distance_seconds"] += duration
            item["light_seconds"] += duration
            item["reading_seconds"] += duration
            item["medium_seconds"]["Print" if scene == "paper" else "Digital"] += (
                duration
            )
            item["near"] += sum(e.metric == "Dis" for e in alerts)
            item["dim"] += sum(e.metric == "Lux" for e in alerts)
            item["breaks"] += sum(e["kind"] == "rest_due" for e in activity["events"])
            item["details"].append(
                {
                    "start": row["start"],
                    "scene": scene,
                    "active_seconds": duration,
                    "events": [
                        {
                            **e.model_dump(),
                            "source": "simulated",
                            "scene_source": "simulated",
                        }
                        for e in alerts
                    ]
                    + [
                        {
                            **e,
                            "started_at": (
                                start + timedelta(seconds=e["source_second"])
                            ).isoformat(sep=" "),
                        }
                        for e in activity["events"]
                    ],
                }
            )
    return table


DEFAULT_DATES = {"ritw": None, "clouclip": "2020-11-21", "simulated": "2026-11-18"}


class ReportTotals(TypedDict):
    coverage_seconds: int
    distance_seconds: int
    light_seconds: int
    reading_seconds: int
    medium_seconds: dict[str, int]
    near: int
    dim: int
    breaks: int


class DayTotals(ReportTotals):
    date: str
    recorded: bool


class ReadingDetail(TypedDict):
    id: str
    covered_seconds: int
    predicted_read_seconds: int
    reference_read_seconds: float
    events: list[ClockEvent]


class SimulatedClockEvent(ClockEvent):
    started_at: str


class SimulatedDetail(TypedDict):
    start: str
    scene: cc.Scene
    active_seconds: int
    events: list[SimulatedClockEvent | cc.Episode]


class EyeReport(TypedDict):
    source: ReportSource
    scene: cc.Scene
    day: date
    week: list[DayTotals]
    totals: ReportTotals
    recorded_days: list[str]
    details: list[ReadingDetail | SimulatedDetail | cc.Episode]


@router.get("/report", response_model=EyeReport)
def report(source: ReportSource, day: date | None = None, scene: cc.Scene = "paper"):
    table = (
        measured_days(scene)
        if source == "clouclip"
        else reading_days()
        if source == "ritw"
        else simulated_days()
    )
    day = day or date.fromisoformat(DEFAULT_DATES[source] or min(table))
    monday = day - timedelta(days=day.weekday())
    if (date.max - monday).days < 6:
        raise HTTPException(422, "请选择一个可以展示完整一周的日期。")
    week = []
    for i in range(7):
        key = (monday + timedelta(days=i)).isoformat()
        item = table.get(key, blank(key))
        week.append({k: v for k, v in item.items() if k != "details"})
    totals = {
        k: sum(item[k] for item in week)
        for k in (
            "coverage_seconds",
            "distance_seconds",
            "light_seconds",
            "reading_seconds",
            "near",
            "dim",
            "breaks",
        )
    }
    media = Counter()
    for item in week:
        media.update(item["medium_seconds"])
    return {
        "source": source,
        "scene": scene,
        "day": day,
        "week": week,
        "totals": {**totals, "medium_seconds": media},
        "recorded_days": sorted(k for k, v in table.items() if v["recorded"]),
        "details": table.get(day.isoformat(), {}).get("details", []),
    }
