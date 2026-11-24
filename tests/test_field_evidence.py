"""Supervised test windows are always rescored from an isolated SQLite fixture."""

import copy
import json
import sqlite3

import pytest

from ml.vision import physical


def event(db, t, silent, sid="fixture"):
    db.execute(
        "INSERT INTO events(session_id,kind,ts,payload) VALUES(?,?,?,?)",
        (sid, "session.privacy", t, json.dumps({"silent": silent})),
    )


def capture(
    db,
    at,
    source="double_tap",
    sid="fixture",
    confirmed=1,
    ua="Mobile iPhone",
    model=None,
    side=None,
):
    db.execute(
        "INSERT INTO captures VALUES(?,?,?,?,?,?,?,?)",
        (f"{sid}-{at}", at, source, confirmed, ua, model, sid, side),
    )


def sample(
    db, metric, at, value, calibration=None, sid="fixture", mode="live", method=None
):
    distance = metric == "distance_cm"
    body = {
        "method": method
        or ("qr-size-proxy-v2" if distance else "center-luma-rec709-v1"),
        "unit": "cm" if distance else "level",
        "value_kind": "estimated" if distance else "measured",
        "quality": "ok",
        "value": value,
        "calibration_id": calibration,
    }
    db.execute(
        "INSERT INTO telemetry VALUES(?,?,?,?,?)",
        (sid, metric, mode, at, json.dumps(body)),
    )


def recorded(phase, result, confirmed=True):
    return {
        "protocol": physical.PROTOCOL,
        "operator_performed": confirmed,
        **(
            {"operator_confirmed_both_displays": confirmed}
            if phase in physical.EYE
            else {}
        ),
        "phase": phase,
        "result": {**result, "pass": False},
    }


@pytest.fixture
def field():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE captures(id,created,source,phone_confirmed,user_agent,camera_model,session_id,tap_side);
        CREATE TABLE alerts(id,session_id,metric,input_mode,started,raised,ended,reason,body,seen);
        CREATE TABLE alert_sources(alert_id,transport,iphone);
        CREATE TABLE telemetry(session_id,metric,input_mode,observed,body);
        CREATE TABLE events(seq INTEGER PRIMARY KEY,session_id,kind,ts,payload);
    """)
    trials = []
    for i in range(5):
        start = i * 12 + 1
        trials.append({"window": [start, start + 6]})
        capture(db, start + 7, side=physical.TAP_SIDES[i])
    single = (65, 71)
    for sec in range(66, 72):
        sample(db, "brightness", sec, 108)
    event(db, 74.5, True)
    event(db, 90, False)
    eye_runs = []
    for i, phase in enumerate(physical.EYE):
        metric, method, kind, unit, low, high = physical.EYE_SPECS[phase]
        start = 101 + i * 50
        trigger = [start, start + 12]
        recovery = [start + 18, start + 30]
        aid = f"a-{i}"
        for sec in range(start + 1, start + 12):
            sample(db, metric, sec, low - 4)
        for sec in range(start + 19, start + 30):
            sample(db, metric, sec, high + 8)
        body = {
            "id": aid,
            "metric": metric,
            "method": method,
            "quality": "ok",
            "value_kind": kind,
            "unit": unit,
            "input_mode": "live",
            "value": low - 4,
        }
        db.execute(
            "INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                aid,
                "fixture",
                metric,
                "live",
                start + 1,
                start + 3,
                start + 19,
                "returned_to_range",
                json.dumps(body),
                start + 4,
            ),
        )
        db.execute("INSERT INTO alert_sources VALUES(?,?,?)", (aid, "lan_https", 1))
        db.execute(
            "INSERT INTO events(session_id,kind,ts,payload) VALUES(?,?,?,?)",
            ("fixture", "alert.raised", start + 3.01, json.dumps(body)),
        )
        db.execute(
            "INSERT INTO events(session_id,kind,ts,payload) VALUES(?,?,?,?)",
            (
                "fixture",
                "alert.cleared",
                start + 19.01,
                json.dumps(
                    {"id": aid, "metric": metric, "reason": "returned_to_range"}
                ),
            ),
        )
        eye_runs.append(
            recorded(phase, {"trigger_window": trigger, "recovery_window": recovery})
        )
    evidence = {
        "session": "fixture",
        "device": "fixture",
        "runs": [
            recorded("double_tap", {"trials": trials}),
            recorded("single_tap", {"window": single}),
            recorded("silent", {"window": [77, 83], "prepared_at": 74}),
            *eye_runs,
        ],
    }
    yield db, evidence
    db.close()


def test_partial_and_full_verification_recompute(field):
    db, evidence = field
    complete = physical.verify(db, evidence)
    assert complete["passed"]
    assert complete["runs"]["double_tap"]["single_capture_hits"] == 5
    assert complete["runs"]["silent"]["parent_enabled_event"]["at"] == 74.5
    evidence["runs"].pop()
    assert physical.verify(db, evidence, physical.TAPS)["passed"]
    assert physical.verify(db, evidence)["missing"] == ["dim_restore"]


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "manual",
        "unconfirmed",
        "desktop",
        "wrong_model",
        "wrong_side",
        "no_side",
        "overlap",
        "fewer",
    ],
)
def test_double_tap_needs_five_independent_confirmed_iphone_records(field, failure):
    db, evidence = field
    trials = evidence["runs"][0]["result"]["trials"]
    if failure == "duplicate":
        capture(db, 5, "camera")
    elif failure == "manual":
        db.execute("UPDATE captures SET source='gesture' WHERE created=8")
    elif failure == "unconfirmed":
        db.execute("UPDATE captures SET phone_confirmed=0 WHERE created=8")
    elif failure == "desktop":
        db.execute("UPDATE captures SET user_agent='Mac' WHERE created=8")
    elif failure == "wrong_model":
        db.execute("UPDATE captures SET camera_model='iPhone 12' WHERE created=8")
    elif failure in ("wrong_side", "no_side"):
        db.execute(
            "UPDATE captures SET tap_side=? WHERE created=8",
            ("right" if failure == "wrong_side" else None,),
        )
    elif failure == "overlap":
        trials[1]["window"] = [9, 15]
    else:
        trials.pop()
    assert not physical.verify(db, evidence, physical.TAPS)["runs"]["double_tap"][
        "pass"
    ]


@pytest.mark.parametrize(
    "failure",
    ["no_samples", "simulated", "other_method", "capture", "short", "unconfirmed"],
)
def test_single_tap_needs_live_rear_samples_and_no_capture_from_any_source(
    field, failure
):
    db, evidence = field
    if failure == "no_samples":
        db.execute("DELETE FROM telemetry WHERE metric='brightness'")
    elif failure == "simulated":
        db.execute(
            "UPDATE telemetry SET input_mode='accelerated' WHERE metric='brightness'"
        )
    elif failure == "other_method":
        db.execute("DELETE FROM telemetry WHERE metric='brightness'")
        for sec in range(65, 72):
            sample(db, "brightness", sec, 100, method="front-camera")
    elif failure == "capture":
        capture(db, 73, "upload")  # Still within the receipt grace period.
    elif failure == "short":
        evidence["runs"][1]["result"]["window"] = (66, 69)
    else:
        evidence["runs"][1]["operator_performed"] = False
    assert not physical.verify(db, evidence, physical.TAPS)["runs"]["single_tap"][
        "pass"
    ]


@pytest.mark.parametrize(
    "failure",
    [
        "no_toggle",
        "wrong_room",
        "stale",
        "same_state",
        "unmuted",
        "capture",
        "unconfirmed",
    ],
)
def test_mute_requires_fresh_parent_transition_entire_window_and_zero_uploads(
    field, failure
):
    db, evidence = field
    if failure == "no_toggle":
        db.execute("DELETE FROM events")
    elif failure == "wrong_room":
        db.execute("UPDATE events SET session_id='other'")
    elif failure == "stale":
        db.execute("UPDATE events SET ts=60 WHERE ts=74.5")
    elif failure == "same_state":
        event(db, 52, True)
    elif failure == "unmuted":
        event(db, 84, False)
        event(db, 85, True)
    elif failure == "capture":
        capture(db, 82, "native_camera")
    else:
        evidence["runs"][2]["operator_performed"] = False
    assert not physical.verify(db, evidence, physical.TAPS)["runs"]["silent"]["pass"]


def test_legacy_and_cross_room_observations_cannot_pass(field):
    db, evidence = field
    for row in evidence["runs"]:
        row.pop("protocol")
        row["result"]["pass"] = True
    evidence["runs"][0]["phase"] = "gesture"
    evidence["runs"][1]["phase"] = "writing"
    assert physical.verify(db, evidence)["missing"] == list(physical.ALL)
    db.execute("UPDATE captures SET session_id='other'")
    evidence["runs"].append(recorded("double_tap", evidence["runs"][0]["result"]))
    assert not physical.verify(db, evidence, ("double_tap",))["passed"]


def test_latest_failed_retry_and_independent_eyecare(field):
    db, evidence = field
    evidence["runs"].append(copy.deepcopy(evidence["runs"][1]))
    evidence["runs"][-1]["operator_performed"] = False
    assert not physical.verify(db, evidence)["passed"]
    assert physical.verify(db, evidence, physical.EYE)["passed"]
    db.execute("DELETE FROM telemetry WHERE metric='distance_cm' AND observed<115")
    assert not physical.verify(db, evidence, physical.EYE)["passed"]


def test_no_shared_window_across_phases(field):
    db, evidence = field
    evidence["runs"][1]["result"]["window"] = (74.5, 80.5)
    for sec in range(75, 81):
        sample(db, "brightness", sec, 100)
    report = physical.verify(db, evidence, physical.TAPS)
    assert all(r["pass"] for r in report["runs"].values())
    assert not report["independent_windows"]
    assert not report["passed"]


def test_append_preserves_old_failures_and_other_recorder(tmp_path):
    dest = tmp_path / "evidence.json"
    initial = {
        "session": "fixture",
        "device": "fixture",
        "runs": [{"phase": "gesture", "result": {"pass": False}}],
    }
    physical.save(dest, initial)
    physical.append_run(
        dest, copy.deepcopy(initial), recorded("double_tap", {"trials": []})
    )
    physical.append_run(
        dest, copy.deepcopy(initial), recorded("single_tap", {"window": [1, 7]})
    )
    assert [r["phase"] for r in json.loads(dest.read_text())["runs"]] == [
        "gesture",
        "double_tap",
        "single_tap",
    ]


def test_five_positive_trials_wait_for_five_operator_ready_clicks(field):
    db, evidence = field
    windows = iter(t["window"] for t in evidence["runs"][0]["result"]["trials"])

    class FakeGuide:
        def __init__(self):
            self.ready_calls = 0

        def ready(self, title, cue):
            self.ready_calls += 1

        def window(self, title, action, cue, seconds):
            expected = physical.SIDE_TEXT[physical.TAP_SIDES[self.ready_calls - 1]]
            assert action == f"现在双击{expected}侧"
            return next(windows)

        def settle(self, seconds):
            assert seconds == physical.GRACE

        def confirm(self, phase):
            assert phase == "double_tap"
            return False

    guide = FakeGuide()
    run = physical.record(db, "fixture", "double_tap", guide)
    assert guide.ready_calls == 5
    assert not run["operator_performed"]
    assert not run["result"]["pass"]


@pytest.mark.parametrize(
    "breakage",
    [
        "fixture_phone",
        "local_transport",
        "accelerated",
        "old_method",
        "missing_marker",
        "no_recovery_sample",
        "other_id",
        "no_raise",
        "no_clear",
        "stale_alert",
        "wrong_phase",
        "parent_not_seen",
        "parent_late",
        "phone_not_confirmed",
        "other_room",
        "legacy",
    ],
)
def test_field_eyecare_rejects_incomplete_or_unrelated_proof(field, breakage):
    db, evidence = field
    if breakage == "fixture_phone":
        db.execute("UPDATE alert_sources SET iphone=0")
    elif breakage == "local_transport":
        db.execute("UPDATE alert_sources SET transport='local'")
    elif breakage == "accelerated":
        db.execute("UPDATE alerts SET input_mode='accelerated'")
    elif breakage == "old_method":
        db.execute("""UPDATE telemetry SET body=json_set(body,'$.method','qr-pinhole-v1')
                      WHERE metric='distance_cm'""")
    elif breakage == "missing_marker":
        db.execute("UPDATE alerts SET reason='signal_lost'")
    elif breakage == "no_recovery_sample":
        db.execute(
            "UPDATE telemetry SET body=json_set(body,'$.value',NULL,'$.quality','missing') WHERE observed=120"
        )
    elif breakage == "other_id":
        db.execute(
            """UPDATE events SET payload=json_set(payload,'$.id','another') WHERE kind='alert.cleared'"""
        )
    elif breakage == "no_raise":
        db.execute("DELETE FROM events WHERE kind='alert.raised'")
    elif breakage == "no_clear":
        db.execute("DELETE FROM events WHERE kind='alert.cleared'")
    elif breakage == "stale_alert":
        db.execute("UPDATE alerts SET started=12")
    elif breakage == "wrong_phase":
        evidence["runs"][3]["result"]["recovery_window"] = [121, 133]
    elif breakage == "parent_not_seen":
        db.execute("UPDATE alerts SET seen=NULL")
    elif breakage == "parent_late":
        db.execute("UPDATE alerts SET seen=200")
    elif breakage == "phone_not_confirmed":
        evidence["runs"][3].pop("operator_confirmed_both_displays")
    elif breakage == "other_room":
        db.execute("UPDATE events SET session_id='x' WHERE kind='alert.cleared'")
    else:
        evidence["runs"][3]["protocol"] = "iphone-double-tap-v2"
    assert not physical.verify(db, evidence, physical.EYE)["passed"]


def test_lighting_needs_real_shadow_and_bright_recovery(field):
    db, evidence = field
    report = physical.verify(db, evidence, physical.EYE)
    assert report["runs"]["dim_restore"]["alerts"][0]["reason"] == "returned_to_range"
    db.execute("""UPDATE telemetry SET body=json_set(body,'$.value',55)
                  WHERE metric='brightness' AND observed>165""")
    assert not physical.verify(db, evidence, physical.EYE)["runs"]["dim_restore"][
        "pass"
    ]


@pytest.mark.parametrize("phase", physical.EYE)
def test_scores_normal_backend_alert_lifecycle(monkeypatch, phase):
    from datetime import UTC, datetime

    from apps.api import sensors

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(sensors.SCHEMA)
    db.execute(
        "CREATE TABLE events(seq INTEGER PRIMARY KEY,session_id,kind,ts,payload)"
    )
    now = [1000.0]
    monkeypatch.setattr(physical.time, "time", lambda: now[0])
    metric, method, kind, unit, low, high = physical.EYE_SPECS[phase]

    def ingest(t, value):
        now[0] = t + 0.05
        observed = sensors.Sample(
            metric=metric,
            method=method,
            unit=unit,
            observed_at=datetime.fromtimestamp(t, UTC),
            value_kind=kind,
            input_mode="live",
            quality="ok",
            value=value,
        )
        sensors.ingest(db, "field", [observed], transport="lan_https", iphone=True)

    for t in range(1001, 1016):
        ingest(t, low - 1)
    db.execute("UPDATE alerts SET seen=1005 WHERE session_id='field'")
    for t in range(1016, 1025):
        ingest(t, high + 1)
    result = physical.score_eye(db, "field", phase, [1000, 1012], [1015.5, 1028])
    assert result["pass"]
    assert result["alerts"][0]["parent_seen"] == 1005
    assert result["recovery_samples"][0]["at"] == 1016
    db.close()
