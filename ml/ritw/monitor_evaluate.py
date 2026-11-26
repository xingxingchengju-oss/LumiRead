"""Rank validation replays and evaluate fixed product labels on whole held-out videos."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from apps.api.monitor import (
    FULL_REST_SECONDS,
    RULE,
    SCORE_POLICY,
    TICKS,
    score,
    timeline,
)

from .monitor_frames import WORK, write_json
from .monitor_panel import panel, reading_intervals
from .sources import ARTIFACTS, CACHE, REVISION, rows


def runs(start, states):
    intervals = []
    for t, state in enumerate(states, start):
        if intervals and intervals[-1][2:] == list(state):
            intervals[-1][1] = t + 1
        else:
            intervals.append([t, t + 1, *state])
    return intervals


def provenance(row, patches):
    folder = WORK / row["id"]
    receipt_ids, models = set(), set()
    # Keep provider identifiers private in the local run cache.
    for p in patches:
        if not p["review"]:
            continue
        for entry in (folder / "reviews").glob(f"{p['start']}-*.json"):
            value = json.loads(entry.read_text())
            if value["observation"] == p["review"]:
                receipt_ids.add(value["receipt"]["request_id"])
                models.add(value["receipt"]["model"])
                break
    camera = CACHE / "sequences" / row["id"] / "rgb-calibration.json"
    return {
        "reviewed_patches": sum(p["review"] is not None for p in patches),
        "provider_models": sorted(models),
        "requests": len(receipt_ids),
        "receipts_sha256": hashlib.sha256(
            "\n".join(sorted(receipt_ids)).encode()
        ).hexdigest(),
        "calibration_sha256": hashlib.sha256(camera.read_bytes()).hexdigest(),
    }


def validation(row, patches, states, points, mixed, audit):
    start = patches[0]["start"]
    spans = reading_intervals(mixed)
    rest_windows = audit["rest"]
    read = [i for i in range(len(states)) if any(a <= start + i < b for a, b in spans)]
    rest = [
        i
        for i in range(len(states))
        if any(a <= start + i < b for a, b in rest_windows)
    ]
    read_recall = sum(states[i][0] == "reading" for i in read) / len(read)
    rest_recall = (
        sum(states[i][0] == "rest" for i in rest) / len(rest) if rest else None
    )
    medium_accuracy = sum(states[i][1] == audit["medium"] for i in read) / len(read)
    rises = any(points[i + 1][2] > points[i][2] for i in read)
    falls = any(points[i + 1][2] < points[i][2] for i in rest)
    unknown = sum(
        a == "unknown" or (a in ("reading", "video") and m == "unknown")
        for a, m in states
    )
    return {
        "id": row["id"],
        "group": row["monitor_group"],
        "medium": audit["medium"],
        "read_seconds": len(read),
        "verified_rest": rest_windows,
        "rest_seconds": len(rest),
        "reading_recall": read_recall,
        "rest_recall": rest_recall,
        "mean_recall": (read_recall + rest_recall) / 2
        if rest_recall is not None
        else None,
        "medium_accuracy": medium_accuracy,
        "unknown_rate": unknown / len(states),
        "eligible": bool(rises and falls and any(b - a > 10 for a, b in rest_windows)),
    }


def test_reference(row):
    group = row["monitor_group"]
    if group == "video":
        device = row["device"]
        if device == "Phone":
            return "video", "phone"
        if device == "Laptop" or (device == "Screen" and "Desktop" in row["tags"]):
            return "video", "computer"
        return "video", "unknown"
    return ("rest", "none") if group == "rest" else ("reading", group)


def held_out_metrics(records):
    activities, media = {}, {}

    def add(table, truth, predicted, seconds):
        s = table.setdefault(truth, Counter())
        s["seconds"] += seconds
        s["correct"] += seconds * (truth == predicted)
        s["undetermined"] += seconds * (predicted in ("unknown", "none"))

    for r in records:
        activity, medium = r["reference"]
        for a, b, pa, pm in r["predictions"]:
            add(activities, activity, pa, b - a)
            if medium not in ("none", "unknown"):
                add(media, medium, pm, b - a)
        activities[activity]["recordings"] += 1
        if medium in media:
            media[medium]["recordings"] += 1
    for buckets in (activities, media):
        for s in buckets.values():
            s["recall"] = s["correct"] / s["seconds"]
            s["undetermined_rate"] = s["undetermined"] / s["seconds"]

    def rate(buckets):
        return sum(s["undetermined"] for s in buckets.values()) / sum(
            s["seconds"] for s in buckets.values()
        )

    return {
        "activity": activities,
        "medium": media,
        "activity_undetermined_rate": rate(activities),
        "medium_undetermined_rate": rate(media),
    }


def simulation():
    spans = [
        ("reading", "phone", 900),
        ("reading", "paper", 1200),
        ("rest", "none", FULL_REST_SECONDS),
    ]
    points, events = score((a, m) for a, m, length in spans for _ in range(length))
    return {
        "source": "模拟",
        "spans": spans,
        "reminders": events,
        "score_by_second": {
            s: round(points[s][2] / TICKS, 2)
            for s in (0, 900, 2100, 2110, 2112, 2460, len(points) - 1)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    args = parser.parse_args()
    refs = json.loads(Path(__file__).with_name("monitor-reference.json").read_text())
    mixed = {r["id"]: r for r in rows("task16_annotations.csv")}
    data, candidates, tests = {}, [], []
    for row in panel():
        seq = row["id"]
        patches = json.loads((WORK / seq / "patches.json").read_text())
        start = patches[0]["start"]
        states = list(timeline(patches))
        details = provenance(row, patches)
        if row["split"] == "val":
            points, _ = score(states, start)
            candidate = validation(row, patches, states, points, mixed[seq], refs[seq])
            candidates.append({**candidate, **details})
            data[seq] = patches
        else:
            tests.append(
                {
                    "id": seq,
                    "group": row["monitor_group"],
                    "reference": test_reference(row),
                    "official_mode": row["mode"],
                    "official_reading": row["reading"],
                    "missing_seconds": sum(len(p["missing"]) for p in patches),
                    "predictions": runs(start, states),
                    **details,
                }
            )
    selected = {}
    for kind in ("paper", "digital"):
        eligible = [c for c in candidates if c["group"] == kind and c["eligible"]]
        if not eligible:
            raise ValueError(
                f"No visually verified {kind} recording with a visible score rise and fall"
            )
        best = min(
            eligible,
            key=lambda c: (
                -c["mean_recall"],
                -c["medium_accuracy"],
                c["unknown_rate"],
                c["id"],
            ),
        )
        selected[kind] = best["id"]
    report = {
        "rule_version": RULE,
        "upstream_revision": REVISION,
        "selected": selected,
        "validation": candidates,
        "test_recordings": tests,
        "test": held_out_metrics(tests),
        "simulation": simulation(),
    }
    write_json(args.out / "monitor-metrics.json", report)
    clips = []
    for kind, seq in selected.items():
        full = data[seq]
        first = next(
            i
            for i, p in enumerate(full)
            if p["activity"] == "reading"
            and p["medium"] == refs[seq]["medium"]
            and p["review"]
        )
        patches = full[first:]
        start = patches[0]["start"]
        points, reminders = score(timeline(patches), start)
        clips.append(
            {
                "id": seq,
                "kind": kind,
                "start": start,
                "end": patches[-1]["end"],
                "patches": patches,
                "points": points,
                "reminders": reminders,
            }
        )
    write_json(
        args.out / "monitor.json",
        {
            "rule_version": RULE,
            "ticks_per_point": TICKS,
            "score_policy": SCORE_POLICY,
            "clips": clips,
        },
    )
    print(
        json.dumps(
            {k: report[k] for k in ("selected", "test", "simulation")},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
