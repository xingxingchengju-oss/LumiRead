import json
from datetime import datetime, timedelta
from itertools import pairwise
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apps.api import clouclip as cc
from apps.api import storage
from apps.api.main import app
from scripts.clouclip_data import DIRECTORY, build


def points(values):
    base = datetime(2020, 11, 21, 9)
    return [
        cc.normalized(
            {
                "line": i + 2,
                "Date": str(base + timedelta(seconds=t)),
                "Dis": dis,
                "Lux": lux,
            },
            base,
        )
        for i, (t, dis, lux) in enumerate(values)
    ]


def edges(result):
    return [(event.metric, event.start_line, event.end_line) for event in result]


def test_exact_pinned_data_and_every_real_prefix():
    assert build() == json.loads((DIRECTORY / "segments.json").read_text())
    _, parts = cc.dataset()
    expected = {
        "stable": [],
        "near": [("Dis", 56353, 56356)],
        "dim": [("Lux", 56770, 56776)],
    }
    for key, (_, samples) in parts.items():
        for j, sample in enumerate(samples, 1):
            assert edges(cc.evaluate(samples[:j])) == [
                (metric, start, end if end <= sample.line else None)
                for metric, start, end in expected[key]
                if start <= sample.line
            ]
        for a, b in pairwise(samples):
            assert a.line + 1 == b.line and a.offset_seconds + 5 == b.offset_seconds


def test_thresholds_hysteresis_short_excursion_and_single_episode():
    obs = points(
        [
            (i * 5, d, l)
            for i, (d, l) in enumerate(
                [
                    (32, 299),
                    (32, 299),
                    (33, 300),  # strict lower limit; reset
                    (32, 299),
                    (32, 299),
                    (32, 299),
                    (30, 250),
                    (30, 250),
                    (35, 350),
                    (34, 349),
                    (35, 350),
                    (35, 350),
                ]
            )
        ]
    )
    out = cc.evaluate(obs)
    assert edges(out) == [("Dis", 7, 13), ("Lux", 7, 13)]
    assert out[0].started_at == obs[5].Date
    assert obs[5].offset_seconds - obs[3].offset_seconds == 10
    assert out[0].ended_at == obs[-1].Date


@pytest.mark.parametrize("bad", [None, 204, 121, 0])
def test_missing_distance_does_not_interrupt_lux_or_claim_recovery(bad):
    r = points(
        [
            (0, 32, 260),
            (5, 32, 260),
            (10, bad, 260),
            (15, 32, 360),
            (20, 32, 360),
            (25, 32, 360),
            (30, 35, 360),
            (35, bad, 360),
            (40, 35, 360),
            (45, 35, 360),
        ]
    )
    assert edges(cc.evaluate(r)) == [("Lux", 4, 6), ("Dis", 7, 11)]
    assert r[2].distance_cm is None and r[2].illuminance_lx == 260


def test_sleep_gap_and_metric_specific_missing_lux():
    r = points(
        [
            (0, 32, 260),
            (5, 32, 260),
            (10, -1, -1),
            (15, 32, 260),
            (20, 32, 260),
            (35, 32, 260),
            (40, 32, None),
            (45, 32, 260),
            (50, 32, 260),
            (55, 32, 260),
            (60, 35, 350),
            (75, 35, 350),
            (80, 35, 350),
        ]
    )
    assert edges(cc.evaluate(r)) == [("Dis", 9, 14), ("Lux", 11, 14)]
    for pair in [(-1, 600), (40, -1)]:
        row = points([(0, *pair)])[0]
        assert row.distance_cm is None and row.illuminance_lx is None


def test_clock_controls_background_auth_restart_and_account_reset(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    clock = [2000.0]
    monkeypatch.setattr(cc, "time", SimpleNamespace(time=lambda: clock[0]))
    with TestClient(app) as near, TestClient(app) as dim, TestClient(app) as stranger:

        def login(client, account):
            result = client.post("/api/v1/demo/login", json={"account_id": account})
            assert result.status_code == 200, result.text
            return result.json()["session_id"]

        b = login(near, "B")
        c = login(dim, "C")
        path = f"/api/v1/sessions/{b}/clouclip"
        cpath = f"/api/v1/sessions/{c}/clouclip"

        def cmd(client, url, action, generation=0, **values):
            res = client.post(
                url + "/control",
                json={"action": action, "generation": generation, **values},
            )
            assert res.status_code == 200, res.text
            return res.json()

        assert near.get(path).json()["segment"]["id"] == "near"
        assert dim.get(cpath).json()["segment"]["id"] == "dim"
        assert stranger.get(path).status_code == 401
        assert dim.get(path).status_code == 403
        assert (
            dim.post(
                path + "/control", json={"action": "play", "generation": 0}
            ).status_code
            == 403
        )
        assert (
            near.post(
                path + "/control", json={"action": "speed", "speed": 3, "generation": 0}
            ).status_code
            == 422
        )
        assert cmd(near, path, "play")["records"][0]["offset_seconds"] == 0
        clock[0] += 7.5
        paused = cmd(near, path, "pause")
        assert paused["position_seconds"] == 7.5 and len(paused["records"]) == 2
        clock[0] += 100
        assert near.get(path).json() == paused
        cmd(near, path, "speed", speed=10)
        cmd(near, path, "play")
        clock[0] += 2
        cc.advance_all()  # no browser request while the server advances past the trigger
        with storage.transaction() as db:
            assert (
                db.execute(
                    "SELECT processed FROM clouclip_playbacks WHERE sid=?", (b,)
                ).fetchone()[0]
                == 6
            )
            assert (
                db.execute(
                    "SELECT end_line FROM clouclip_events WHERE sid=?", (b,)
                ).fetchone()[0]
                is None
            )
        storage.initialize()  # persisted after an application restart
        assert near.get(path).json()["events"][0]["start_line"] == 56353
        clock[0] += 3
        cc.advance_all()
        finished = near.get(path).json()
        assert finished["status"] == "finished" and len(finished["records"]) == 11
        assert finished["events"][0]["end_line"] == 56356
        assert dim.get(cpath).json()["records"] == []
        # Replaying from the beginning refreshes this timeline; retried requests do not restart it twice.
        again = cmd(near, path, "replay")
        assert (
            again["generation"] == 1
            and len(again["records"]) == 1
            and again["events"] == []
        )
        clock[0] += 2
        assert cmd(near, path, "replay")["position_seconds"] == 20
        cmd(near, path, "speed", generation=1, speed=1)
        clock[0] += 100
        assert near.get(path).json()["events"] == finished["events"]
        assert near.get(path).json()["records"] == finished["records"]
        # A reset invalidates the session key and deletes only its sensor timeline.
        reset = near.post("/api/v1/demo/reset", json={"session_id": b})
        assert reset.status_code == 200, reset.text
        b2 = reset.json()["session_id"]
        assert b != b2 and near.get(path).status_code == 403
        assert near.get(f"/api/v1/sessions/{b2}/clouclip").json()["status"] == "ready"
        with storage.transaction() as db:
            for table in ("clouclip_events", "clouclip_playbacks"):
                assert not db.execute(
                    f"SELECT 1 FROM {table} WHERE sid=?", (b,)
                ).fetchone()
        assert dim.get(cpath).json()["segment"]["id"] == "dim"


def test_no_replay_for_legacy_session_or_phone(desks):
    parent, phone, sid = desks
    path = f"/api/v1/sessions/{sid}/clouclip"
    assert parent.get(path).status_code == 404
    with storage.transaction(True) as db:
        cc.bind(db, sid, "stable")
    assert phone.get(path).status_code == 403
    assert (
        phone.post(
            path + "/control", json={"action": "play", "generation": 0}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("segment", ["stable", "near", "dim"])
def test_playback_at_every_source_timestamp_at_all_speeds(
    tmp_path, monkeypatch, segment
):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    storage.initialize()
    _, samples = cc.dataset()[1][segment]
    observed = []
    for speed in (1, 4, 10):
        sid = f"{segment}-{speed}"
        with storage.transaction(True) as db:
            db.execute("INSERT INTO learners(id) VALUES(?)", (sid,))
            db.execute(
                "INSERT INTO sessions(id,learner,created) VALUES(?,?,0)", (sid, sid)
            )
            cc.bind(db, sid, segment)
            cc.control(
                db, sid, cc.Control(action="speed", speed=speed, generation=0), 1000
            )
            cc.control(db, sid, cc.Control(action="play", generation=0), 1000)
            trace = []
            for index, sample in enumerate(samples):
                due = 1000 + sample.offset_seconds / speed
                if index:
                    before = cc.state(db, sid, due - 0.001)
                    assert len(before.records) == index
                playback = cc.state(db, sid, due)
                assert playback.records == samples[: index + 1]
                trace.append(edges(playback.events))
            assert playback.status == "finished"
            observed.append(trace)
    assert observed[0] == observed[1] == observed[2]
