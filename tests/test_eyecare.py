import json
from collections import Counter
from datetime import date
from statistics import mean

import pytest
from fastapi.testclient import TestClient

from apps.api import eyecare
from apps.api.main import app


@pytest.mark.parametrize(
    "scene,limit", [("electronic", 1800), ("writing", 2400), ("paper", 2400)]
)
def test_timer_boundaries_idempotency_and_interrupted_rest(scene, limit):
    def evaluate(parts):
        spans = []
        t = 0
        for state, length in parts:
            spans.append(eyecare.Span(state=state, start=t, end=t + length))
            t += length
        return eyecare.clock(eyecare.Clock(source="manual", scene=scene, spans=spans))

    parts = [("active", limit - 1), ("away", 8), ("unknown", 4)]
    assert evaluate(parts)["events"] == []
    parts += [("active", 1), ("rest", 599)]
    before = evaluate(parts)
    assert [(e["kind"], e["source_second"]) for e in before["events"]] == [
        ("rest_due", limit + 12)
    ]
    assert before["missing_seconds"] == 4
    parts += [("away", 1), ("rest", 599)]
    assert len(evaluate(parts)["events"]) == 1
    parts += [("rest", 1), ("active", limit), ("end", 0)]
    result = evaluate(parts)
    assert [e["kind"] for e in result["events"]] == [
        "rest_due",
        "rest_completed",
        "rest_due",
    ]
    assert all(
        e["source"] == "manual" and e["scene"] == scene for e in result["events"]
    )
    assert result["active_seconds"] == 2 * limit and result["bout_seconds"] == 0
    assert evaluate(parts) == result


def test_predicted_medium_switch_and_missing_time_use_the_recording_clock():
    record = {
        "evaluation": [90, 2500],
        "intervals": [[90, 390, 1, 1], [390, 2190, 1, 2], [2200, 2300, 0, 0]],
    }
    result = eyecare.predicted_clock(record)
    assert result["active_seconds"] == 2100 and result["missing_seconds"] == 210
    assert [
        (e["kind"], e["source_second"], e["scene"], e["scene_source"])
        for e in result["events"]
    ] == [("rest_due", 2190, "electronic", "model")]
    # A long gap restarts the reading bout without claiming the participant rested.
    record["evaluation"] = [90, 3690]
    record["intervals"].append([3090, 3690, 1, 1])
    result = eyecare.predicted_clock(record)
    assert result["bout_seconds"] == 600 and len(result["events"]) == 1


def test_reports_sum_only_the_selected_source_and_leave_missing_dates_unknown():
    sim = eyecare.report("simulated")
    assert len(sim["week"]) == 7 and all(d["recorded"] for d in sim["week"])
    assert sim["totals"]["medium_seconds"] == {"Print": 268 * 60, "Digital": 193 * 60}
    assert [sim["totals"][k] for k in ("reading_seconds", "near", "dim", "breaks")] == [
        461 * 60,
        8,
        4,
        6,
    ]
    for item in sim["details"]:
        assert all(
            e["source"] == "simulated" and e["started_at"] for e in item["events"]
        )
    measured = eyecare.report("clouclip")
    assert (
        measured["totals"]["reading_seconds"] == 0 and measured["totals"]["near"] == 911
    )
    assert all(
        e["source"] == "Clouclip" and e["scene"] == "paper" for e in measured["details"]
    )
    same_week = eyecare.report("clouclip", day=date(2020, 11, 17))
    assert measured["totals"] == same_week["totals"]
    empty = eyecare.report("ritw", day=date(2026, 11, 18))
    assert empty["details"] == [] and not any(d["recorded"] for d in empty["week"])
    reading = eyecare.report("ritw")
    assert (
        sum(reading["totals"]["medium_seconds"].values())
        == reading["totals"]["reading_seconds"]
    )
    assert (
        sum(d["reading_seconds"] for d in reading["week"])
        == reading["totals"]["reading_seconds"]
    )


def test_public_routes_with_no_parent_account(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    with TestClient(app) as client:
        prefix = "/api/v1/eye-care"
        for source in ("ritw", "clouclip", "simulated"):
            response = client.get(prefix + "/report", params={"source": source})
            assert response.status_code == 200 and response.json()["source"] == source
        clip = client.get(prefix + "/research").json()
        assert (
            len(clip["clips"]) == 30
            and clip["metrics"]["splits"]["train"]["recordings"] == 48
        )
        assert client.get(prefix + "/preview/0").status_code == 404
        assert (
            client.get(prefix + "/excerpts/dim?scene=phone").json()["distance_limit_cm"]
            == 40
        )
        response = client.post(
            prefix + "/clock",
            json={
                "scene": "paper",
                "source": "manual",
                "spans": [
                    {"state": "active", "start": 5, "end": 6},
                    {"state": "rest", "start": 4, "end": 5},
                ],
            },
        )
        assert response.status_code == 422


def test_frozen_ritw_test_scores_recompute_from_each_sequence():
    metrics = json.loads((eyecare.RITW / "metrics.json").read_text())
    recordings = metrics["inventory"]
    assert len({r["id"] for r in recordings}) == len(recordings) == 96
    for split, quota in metrics["quotas_per_stratum"].items():
        group = [r for r in recordings if r["split"] == split]
        assert len({r["group"] for r in group}) == 6
        assert set(Counter(r["group"] for r in group).values()) == {quota}
        assert sum(r["seconds"] for r in group) == metrics["splits"][split]["seconds"]
    clips = eyecare.research()["clips"]
    assert {c["id"] for c in clips} == {
        r["id"] for r in recordings if r["split"] == "test"
    }
    for name, key in [("official", "intervals"), ("logistic", "baseline_intervals")]:
        binary = Counter()
        support = Counter()
        correct = Counter()
        hard = Counter()
        errors = []
        for c in clips:
            predicted = 0
            coverage = 0
            truth_seconds = 0
            previous = c["evaluation"][0]
            for a, b, r, m in c[key]:
                assert previous <= a < b <= c["evaluation"][1]
                previous = b
                coverage += b - a
                truth_seconds += sum(
                    max(0, min(b, y) - max(a, x)) for x, y in c["reference_intervals"]
                )
                for t in range(a, b):
                    y = int(any(x <= t < end for x, end in c["reference_intervals"]))
                    medium = c["reference_medium"] if y else 0
                    binary[y, r] += 1
                    if medium >= 0:
                        support[medium] += 1
                        correct[medium] += int(m == medium)
                    if c["group"] == "hard_negative":
                        hard[r] += 1
                predicted += (b - a) * r
            assert coverage == c["covered_seconds"]
            assert truth_seconds == pytest.approx(c["reference_read_seconds"])
            if key == "intervals":
                assert (
                    predicted
                    == c["clock"]["active_seconds"]
                    == c["predicted_read_seconds"]
                )
            errors.append(abs(predicted - truth_seconds))
        expected = metrics[name]
        assert sum(binary.values()) == metrics["splits"]["test"]["seconds"]
        assert 2 * binary[1, 1] / (
            2 * binary[1, 1] + binary[0, 1] + binary[1, 0]
        ) == pytest.approx(expected["read_f1"])
        for i, label in enumerate(eyecare.research()["classes"]):
            assert support[i] == expected["medium_support"][label]
            assert correct[i] / support[i] == pytest.approx(
                expected["medium_recall"][label]
            )
        assert mean(errors) == pytest.approx(expected["duration_mae_seconds"])
        assert hard[1] / sum(hard.values()) == pytest.approx(
            expected["hard_false_positive_rate"]
        )
