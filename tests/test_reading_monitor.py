import json
from collections import Counter
from itertools import pairwise, repeat

import pytest
from fastapi.testclient import TestClient

from apps.api import eyecare
from apps.api.main import app
from apps.api.monitor import TICKS, decide, fuse, score, timeline, vote_patches


def sight(activity, medium):
    return {"activity": activity, "medium": medium, "summary": "测试画面", "frames": []}


def test_original_clock_votes_tie_missing_and_periodic_review():
    votes = dict.fromkeys(range(2, 48), 1)
    del votes[10]
    votes.update(dict.fromkeys((7, 8, 9), 0))
    ps = vote_patches(2, 48, votes)
    assert [(p["start"], p["end"]) for p in ps][:2] == [(2, 7), (7, 14)]
    assert ps[-1]["end"] == 48
    assert ps[1]["read_votes"] == ps[1]["nonread_votes"] == 3
    assert "tie" in ps[1]["reasons"] and ps[1]["missing"] == [10]
    assert "periodic" in ps[-1]["reasons"]
    seen = []

    def review(p):
        seen.append(p["start"])
        return (
            sight("video", "computer") if p["start"] == 7 else sight("reading", "phone")
        )

    fuse(ps, review)
    states = list(timeline(ps))
    assert states[7 - 2] == ("video", "computer")
    assert states[10 - 2] == ("unknown", "unknown")
    assert seen == [p["start"] for p in ps if p["reasons"]]
    assert ps[3]["review"] is None and ps[3]["evidence_start"] == 14
    empty = vote_patches(0, 7, {})
    fuse(empty, lambda _: pytest.fail("Missing seconds cannot be recovered by RGB"))
    assert list(timeline(empty)) == [("unknown", "unknown")] * 7


def test_fusion_needs_positive_rest_evidence_and_honors_subtitled_video():
    p = vote_patches(0, 7, dict.fromkeys(range(7), 0))[0]
    assert decide(p, None) == ("unknown", "unknown")
    assert decide(p, sight("rest", "none")) == ("rest", "none")
    p["read_votes"], p["nonread_votes"] = 7, 0
    assert decide(p, sight("video", "unknown")) == ("video", "unknown")
    assert decide(p, sight("video", "screen")) == ("video", "unknown")
    assert decide(p, sight("reading", "unknown")) == ("reading", "unknown")


def test_winner_rates_mixed_six_second_settlement_and_independent_clocks():
    p = vote_patches(0, 7, {0: 1, 1: 1, 2: 1, 3: 1, 4: 0, 5: 0})
    fuse(p, lambda _: sight("reading", "phone"))
    points, _ = score(timeline(p))
    assert points[5] == (5, 0, 0)
    assert points[6] == points[7] == (6, 0, TICKS // 3)
    states = (
        [("reading", "phone")] * 7
        + [("reading", "unknown")] * 2
        + [("reading", "paper")] * 5
    )
    points, _ = score(states + [("video", "unknown")] * 6)
    assert points[-7] == (14, 0, 168 + 28 + 5 * 21)
    assert points[-1] == (14, 6, 168 + 28 + 5 * 21 + 168)


@pytest.mark.parametrize(
    "activity,medium,minutes",
    [
        ("reading", "phone", 30),
        ("reading", "computer", 35),
        ("reading", "paper", 40),
        ("reading", "other_text", 40),
        ("video", "phone", 30),
        ("video", "computer", 30),
    ],
)
def test_homogeneous_thresholds_and_saturation(activity, medium, minutes):
    points, events = score(repeat((activity, medium), minutes * 60 + 30))
    assert events == [minutes * 60] and points[-1][2] == 100 * TICKS


def test_simulated_long_record_and_interrupted_recovery():
    load = [("reading", "phone")] * 900 + [("reading", "paper")] * 1200
    rest = ("rest", "none")
    points, events = score(load + [rest] * 360)
    assert points[900][2] == 50 * TICKS and points[2100][2] == 100 * TICKS
    assert events == [2100] and points[2110][2] == 100 * TICKS
    assert round(points[2112][2] / TICKS, 2) == 99.43 and points[-1] == (2100, 0, 0)
    points, events = score(
        load
        + [rest] * 9
        + [("unknown", "unknown")]
        + [rest] * 11
        + [("video", "unknown")] * 6
    )
    assert points[2120][2] == 100 * TICKS and points[2121][2] == 100 * TICKS - 144
    assert events == [2100, 2127]


def test_published_monitor_and_held_out_results():
    with TestClient(app) as client:
        response = client.get("/api/v1/eye-care/monitor")
        assert response.status_code == 200
        data = response.json()
    assert [c["kind"] for c in data["clips"]] == ["paper", "digital"]
    report = json.loads((eyecare.RITW / "monitor-metrics.json").read_text())
    assert Counter(r["group"] for r in report["validation"]) == {
        "paper": 10,
        "digital": 5,
    }
    assert sum(r["group"] == "video" for r in report["test_recordings"]) == 8
    assert not (
        {r["id"] for r in report["validation"]}
        & {r["id"] for r in report["test_recordings"]}
    )
    for clip in data["clips"]:
        points, reminders = score(timeline(clip["patches"]), clip["start"])
        assert [list(x) for x in points] == clip["points"] and reminders == clip[
            "reminders"
        ]
        assert any(a[2] < b[2] for a, b in pairwise(points))
        assert any(a[2] > b[2] for a, b in pairwise(points))
        assert report["selected"][clip["kind"]] == clip["id"]


def test_held_out_recalls_include_all_reference_seconds_and_abstentions():
    report = json.loads((eyecare.RITW / "monitor-metrics.json").read_text())
    for axis, index in (("activity", 0), ("medium", 1)):
        for label, counts in report["test"][axis].items():
            recordings = [
                r for r in report["test_recordings"] if r["reference"][index] == label
            ]
            predictions = Counter()
            for recording in recordings:
                for start, end, activity, medium in recording["predictions"]:
                    predictions[(activity, medium)[index]] += end - start
                if recording["group"] == "video":
                    assert (
                        recording["official_reading"] == "True"
                        and recording["official_mode"] == "Videos"
                    )
            total = predictions.total()
            assert (counts["recordings"], counts["seconds"]) == (len(recordings), total)
            assert counts["recall"] == predictions[label] / total
            assert (
                counts["undetermined_rate"]
                == (predictions["unknown"] + predictions["none"]) / total
            )
    assert report["simulation"]["source"] == "模拟"
    assert report["simulation"]["score_by_second"] == {
        "0": 0,
        "900": 50,
        "2100": 100,
        "2110": 100,
        "2112": 99.43,
        "2460": 0,
    }
