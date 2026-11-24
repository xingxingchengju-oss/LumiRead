"""Persist observations by source, and count continuous threshold crossings once."""

import json
import time
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .storage import event as storage_event
from .storage import transaction, uid

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry(
 id INTEGER PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions,metric TEXT NOT NULL,
 input_mode TEXT NOT NULL,observed REAL NOT NULL,body TEXT NOT NULL,
 UNIQUE(session_id,metric,input_mode,observed));
CREATE TABLE IF NOT EXISTS alerts(id TEXT PRIMARY KEY,session_id TEXT NOT NULL REFERENCES sessions,
 metric TEXT NOT NULL,input_mode TEXT NOT NULL,started REAL NOT NULL,raised REAL NOT NULL,ended REAL,
 reason TEXT,body TEXT NOT NULL,seen REAL);
CREATE TABLE IF NOT EXISTS alert_sources(alert_id TEXT PRIMARY KEY REFERENCES alerts,
 transport TEXT NOT NULL,iphone INTEGER NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS active_alert ON alerts(session_id,metric,input_mode) WHERE ended IS NULL;
CREATE TABLE IF NOT EXISTS sensor_states(session_id TEXT NOT NULL REFERENCES sessions,metric TEXT NOT NULL,
 input_mode TEXT NOT NULL,last REAL NOT NULL,pending REAL, PRIMARY KEY(session_id,metric,input_mode));
"""
SPEC = {
    "distance_cm": ("cm", "estimated", "qr-pinhole-v1", 10000),
    "brightness": ("level", "measured", "center-luma-rec709-v1", 255),
    "head_tilt_deg": ("deg", "estimated", "eye-line-roll-v1", 180),
    "reading_seconds": ("s", "measured", "foreground-reading-clock-v1", 864000),
}


class Sample(BaseModel):
    metric: Literal["distance_cm", "brightness", "head_tilt_deg", "reading_seconds"]
    value: float | None = Field(allow_inf_nan=False)
    unit: str
    value_kind: Literal["measured", "estimated", "simulated"]
    input_mode: Literal["live", "accelerated"]
    method: str
    quality: Literal["ok", "missing"]
    calibration_id: str | None = Field(default=None, max_length=160)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def consistent(self):
        if self.observed_at.timestamp() > time.time() + 60:
            raise ValueError("Please synchronize the device clock")
        unit, kind, method, maximum = SPEC[self.metric]
        if self.input_mode == "accelerated":
            if self.metric != "reading_seconds":
                raise ValueError("Only the reading timer supports acceleration")
            kind, method = "simulated", "demo-clock-300x-v1"
        fixed_marker = (
            self.metric == "distance_cm" and self.method == "qr-size-proxy-v2"
        )
        if fixed_marker:
            method = "qr-size-proxy-v2"
            if self.calibration_id is not None:
                raise ValueError("Fixed-marker estimates carry no manual calibration")
        if (self.unit, self.value_kind, self.method) != (unit, kind, method):
            raise ValueError(
                "Source, unit and method must describe the observed metric"
            )
        if (self.value is None) != (self.quality == "missing"):
            raise ValueError("Missing samples require a null value")
        minimum = -180 if self.metric == "head_tilt_deg" else 0
        if self.value is not None and not minimum <= self.value <= maximum:
            raise ValueError("Value outside instrument range")
        if (
            self.metric == "distance_cm"
            and not fixed_marker
            and self.value is not None
            and not self.calibration_id
        ):
            raise ValueError("Distance requires calibration")
        return self


class RearCameraSample(Sample):
    """Live submissions from the wearer camera; historical samples remain readable."""

    metric: Literal["distance_cm", "brightness", "reading_seconds"]


class Batch(BaseModel):
    samples: list[RearCameraSample] = Field(min_length=1, max_length=100)


def stamp(t):
    return datetime.fromtimestamp(t, UTC).isoformat() if t is not None else None


def alert(row):
    return {
        **json.loads(row["body"]),
        "id": row["id"],
        "started_at": stamp(row["started"]),
        "ended_at": stamp(row["ended"]),
        "reason": row["reason"],
    }


def close(db, sid, row, when, reason):
    db.execute(
        "UPDATE alerts SET ended=?,reason=? WHERE id=?", (when, reason, row["id"])
    )
    storage_event(
        db,
        sid,
        "alert.cleared",
        {"id": row["id"], "metric": row["metric"], "reason": reason},
    )


def end_stream(db, stream, when, reason):
    key = (stream["session_id"], stream["metric"], stream["input_mode"])
    active = db.execute(
        "SELECT * FROM alerts WHERE session_id=? AND metric=? AND input_mode=? AND ended IS NULL",
        key,
    ).fetchone()
    if active:
        close(db, key[0], active, when, reason)
    previous = db.execute(
        "SELECT body FROM telemetry WHERE session_id=? AND metric=? AND input_mode=? ORDER BY observed DESC LIMIT 1",
        key,
    ).fetchone()
    if previous:
        sample = json.loads(previous["body"])
        if sample["quality"] != "missing":
            at = max(when, stream["last"] + 0.0001)
            sample.update(value=None, quality="missing", observed_at=stamp(at))
            db.execute(
                "INSERT OR IGNORE INTO telemetry(session_id,metric,input_mode,observed,body) VALUES(?,?,?,?,?)",
                (*key, at, json.dumps(sample)),
            )
            storage_event(
                db, key[0], "telemetry.updated", {"metric": key[1], "reason": reason}
            )
    db.execute(
        "DELETE FROM sensor_states WHERE session_id=? AND metric=? AND input_mode=?",
        key,
    )


def stop(db, sid, reason):
    for row in db.execute(
        "SELECT * FROM sensor_states WHERE session_id=?", (sid,)
    ).fetchall():
        end_stream(db, row, time.time(), reason)


def expire_stale(now=None):
    now = time.time() if now is None else now
    cutoff = now - 15
    with transaction() as db:
        if not db.execute(
            "SELECT 1 FROM sensor_states WHERE last<? LIMIT 1", (cutoff,)
        ).fetchone():
            return
    with transaction(True) as db:
        for row in db.execute(
            "SELECT * FROM sensor_states WHERE last<?", (cutoff,)
        ).fetchall():
            end_stream(db, row, row["last"] + 15, "signal_lost")


def state(metric, value):
    if value is None:
        return False, True
    if metric == "distance_cm":
        return value < 33, value >= 35
    if metric == "brightness":
        return value < 65, value >= 75
    if metric == "head_tilt_deg":
        return abs(value) >= 15, abs(value) <= 12
    return value >= 2700, value < 2700


def ingest(db, sid, samples, transport="local", iphone=False):
    accepted = 0
    for sample in sorted(samples, key=lambda s: s.observed_at):
        key = (sid, sample.metric, sample.input_mode)
        observed = sample.observed_at.timestamp()
        raw = sample.model_dump_json()
        if not db.execute(
            "INSERT OR IGNORE INTO telemetry(session_id,metric,input_mode,observed,body) VALUES(?,?,?,?,?)",
            (*key, observed, raw),
        ).rowcount:
            continue
        accepted += 1
        previous = db.execute(
            "SELECT * FROM sensor_states WHERE session_id=? AND metric=? AND input_mode=?",
            key,
        ).fetchone()
        if not previous:
            latest = db.execute(
                "SELECT MAX(observed) FROM telemetry WHERE session_id=? AND metric=? AND input_mode=?",
                key,
            ).fetchone()[0]
            if observed < latest or observed < time.time() - 15:
                continue
        if previous and observed <= previous["last"]:
            continue
        active = db.execute(
            "SELECT * FROM alerts WHERE session_id=? AND metric=? AND input_mode=? AND ended IS NULL",
            key,
        ).fetchone()
        pending = previous["pending"] if previous else None
        if previous and observed - previous["last"] > 15:
            if active:
                close(db, sid, active, previous["last"], "signal_lost")
                active = None
            pending = None
        unsafe, recovered = state(sample.metric, sample.value)
        if active:
            if recovered:
                close(
                    db,
                    sid,
                    active,
                    observed,
                    "signal_lost" if sample.value is None else "returned_to_range",
                )
            elif unsafe:
                db.execute("UPDATE alerts SET body=? WHERE id=?", (raw, active["id"]))
        elif unsafe:
            pending = observed if pending is None else pending
            if sample.metric == "reading_seconds" or observed - pending >= 2:
                aid = uid()
                db.execute(
                    "INSERT INTO alerts(id,session_id,metric,input_mode,started,raised,body) VALUES(?,?,?,?,?,?,?)",
                    (aid, *key, pending, time.time(), raw),
                )
                db.execute(
                    "INSERT INTO alert_sources VALUES(?,?,?)",
                    (aid, transport, int(iphone)),
                )
                storage_event(
                    db,
                    sid,
                    "alert.raised",
                    {"id": aid, **sample.model_dump(mode="json")},
                )
        if not unsafe:
            pending = None
        db.execute(
            "INSERT INTO sensor_states VALUES(?,?,?,?,?) ON CONFLICT(session_id,metric,input_mode) DO UPDATE SET last=excluded.last,pending=excluded.pending",
            (*key, observed, pending),
        )
    if accepted:
        storage_event(db, sid, "telemetry.updated", {"accepted": accepted})
    return {
        "accepted": accepted,
        "active_alerts": [
            alert(row)
            for row in db.execute(
                "SELECT * FROM alerts WHERE session_id=? AND ended IS NULL ORDER BY raised DESC",
                (sid,),
            )
        ],
    }
