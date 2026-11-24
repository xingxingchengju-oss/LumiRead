"""Materialize local-only authentic demo histories using the preregistered non-training splits."""

import argparse
import csv
import hashlib
import io
import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from .common import CACHE, DATA, SKILLS, json_read, sha256
from .prepare import ARCHIVE, MEMBER, fetch, prepare


def eligible(events, rule):
    counts = Counter(skill for _, skill, _ in events)
    n = len(events)
    largest = max(counts.values(), default=0)
    return (
        rule["min_attempts"] <= n <= rule.get("max_attempts", float("inf"))
        and len(counts) >= rule.get("min_distinct_skills", 1)
        and largest >= rule.get("min_dominant_count", 0)
        and largest >= rule.get("min_dominant_share", 0) * n
    )


def rank(role, student):
    return hashlib.sha256(f"lumiread-demo-v1|{role}|{student}".encode()).hexdigest()


def split_records(split):
    import json

    path = CACHE / f"{split}.jsonl"
    if (
        sha256(path)
        != json_read(DATA / "summary.json")["splits"][split]["sequence_sha256"]
    ):
        raise ValueError(f"Unverified split: {split}")
    return [json.loads(line) for line in path.read_text().splitlines()]


def pick(pools, rulebook):
    selected, used = {}, set()
    for role in rulebook["role_order"]:
        rule = rulebook["roles"][role]
        for split in rulebook["pool_order"]:
            candidates = [
                (student, events)
                for student, events in pools[split]
                if student not in used and eligible(events, rule)
            ]
            if candidates:
                student, events = min(candidates, key=lambda row: rank(role, row[0]))
                used.add(student)
                selected[role] = (split, student, events)
                break
        else:
            raise ValueError(
                f"No non-training learner matched the registered rule for {role}"
            )
    return selected


def build(archive=ARCHIVE):
    fetch(archive)
    summary = json_read(DATA / "demo_selection.json")
    if sha256(archive) != summary["archive_sha256"]:
        raise ValueError("Source archive mismatch")
    selected = pick({s: split_records(s) for s in summary["pool_order"]}, summary)
    # Check the actual CSV header. The only time columns in this pinned file are durations.
    with zipfile.ZipFile(archive) as z, z.open(MEMBER) as stream:
        fields = csv.DictReader(io.TextIOWrapper(stream, encoding="latin1")).fieldnames
    time_fields = [
        field
        for field in fields
        if any(x in field.lower() for x in ("time", "date", "timestamp", "ms_"))
    ]
    if set(time_fields) != {"overlap_time", "ms_first_response"}:
        raise ValueError(
            "Source time columns changed; inspect the new release before importing"
        )
    accounts = []
    for role, (split, student, events) in selected.items():
        counts = Counter(i for _, i, _ in events)
        accounts.append(
            {
                "id": role,
                "label": summary["roles"][role]["label"],
                "split": split,
                "learner_hash": hashlib.sha256(
                    f"lumiread-local-learner|{student}".encode()
                ).hexdigest(),
                "attempt_count": len(events),
                "skill_counts": {s: counts[i] for i, s in enumerate(SKILLS)},
                "events": [
                    {
                        "problem_log_id": order,
                        "skill": SKILLS[i],
                        "correct": bool(c),
                        "observed_at": None,
                    }
                    for order, i, c in events
                ],
            }
        )
    return {
        "schema_version": 1,
        "source": summary["source"],
        "source_sha256": summary["archive_sha256"],
        "selection_sha256": sha256(DATA / "demo_selection.json"),
        "time_basis": "problem_log_id",
        "time_field": None,
        "source_order_field": "order_id",
        "duration_fields": time_fields,
        "time_note": "原始数据提供可排序的问题日志编号，未发布单题绝对作答时间。两个时间字段均为毫秒时长。",
        "accounts": accounts,
    }


def materialize(path=DATA / "demo_accounts.json", archive=ARCHIVE):
    import json

    result = build(archive)
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
        temp = Path(f.name)
    os.replace(temp, path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        default=ARCHIVE,
        help="Exact publisher/mirror ZIP, optionally already downloaded",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the local file by independent selection",
    )
    args = parser.parse_args()
    if prepare(args.archive) != json_read(DATA / "summary.json"):
        raise SystemExit("Rebuilt cohort differs from the frozen source manifest")
    if args.check:
        result = build(args.archive)
        if json_read(DATA / "demo_accounts.json") != result:
            raise SystemExit("Local demo histories differ from their authentic source")
    else:
        result = materialize(archive=args.archive)
    for account in result["accounts"]:
        print(
            account["id"],
            account["label"],
            account["split"],
            account["attempt_count"],
            "eligible responses",
        )
