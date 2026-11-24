"""Rebuild the private student sequences from the pinned, non-collapsed corrected release."""

import argparse
import csv
import hashlib
import io
import json
import tempfile
import urllib.request
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from .common import CACHE, DATA, SEED, SKILLS, SPLITS, json_read, json_write, sha256

SOURCE = (
    "https://base.ustc.edu.cn/data/ASSISTment/2009_skill_builder_data_corrected.zip"
)
ARCHIVE_HASH = "10c4fa76ae9410d8577cf9604cf21f8eed029552717a4b281d64945cf44ebe46"
MEMBER = "skill_builder_data_corrected.csv"
ARCHIVE = CACHE / "assistments2009.zip"


def fetch(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            destination = Path(tmp.name)
        try:
            urllib.request.urlretrieve(SOURCE, destination)
            if sha256(destination) != ARCHIVE_HASH:
                raise ValueError("Downloaded archive does not match the pinned SHA-256")
            destination.replace(path)
        finally:
            destination.unlink(missing_ok=True)
    if sha256(path) != ARCHIVE_HASH:
        raise ValueError(f"Incorrect archive SHA-256 at {path}")


def split_students(students):
    def digest(student):
        return hashlib.sha256(f"assist09:{SEED}:{student}".encode()).hexdigest()

    ordered = sorted(students, key=digest)
    n = len(ordered)
    boundaries = [0, n * 70 // 100, n * 85 // 100, n]
    return {
        split: ordered[a:b] for split, a, b in zip(SPLITS, boundaries, boundaries[1:])
    }


def prepare(archive=ARCHIVE):
    CACHE.mkdir(parents=True, exist_ok=True)
    fetch(archive)
    mapping = json_read(DATA / "skill_mapping.json")
    reverse = {
        label: i for i, skill in enumerate(SKILLS) for label in mapping[skill]["labels"]
    }
    source_rows = Counter()
    # Only mapped main-question history is consumed. Group tags before creating targets.
    events = {}
    counts = Counter()
    with zipfile.ZipFile(archive) as zipped, zipped.open(MEMBER) as member:
        reader = csv.DictReader(io.TextIOWrapper(member, encoding="latin1"))
        for row in reader:
            counts["raw_tag_rows"] += 1
            if row["original"] != "1" or row["answer_type"] == "open_response":
                continue
            label = row["skill_name"].strip()
            if label not in reverse:
                continue
            counts["eligible_mapped_tag_rows"] += 1
            source_rows[label] += 1
            student, order = row["user_id"], int(row["order_id"])
            correct = int(row["correct"])
            if correct not in {0, 1}:
                raise ValueError("Source correctness must be binary")
            event = events.setdefault(
                (student, order), (correct, row["problem_id"], set())
            )
            if event[:2] != (correct, row["problem_id"]):
                raise ValueError(
                    "Conflicting target or item for a student and order_id"
                )
            event[2].add(reverse[label])
    students = defaultdict(list)
    for (student, order), (correct, _, skills) in events.items():
        if len(skills) == 1:
            students[student].append([order, next(iter(skills)), correct])
        else:
            counts["ambiguous_multi_category_events_excluded"] += 1
    groups = split_students(students)
    summaries = {}
    for split, members in groups.items():
        positives, attempts = Counter(), Counter()
        for student in members:
            students[student].sort()
            for _, skill, correct in students[student]:
                attempts[skill] += 1
                positives[skill] += correct
        if set(attempts) != set(range(len(SKILLS))):
            raise ValueError(f"Missing skill in {split}")
        target = CACHE / f"{split}.jsonl"
        with target.open("w", encoding="utf-8") as out:
            for member in members:
                out.write(
                    json.dumps([member, students[member]], separators=(",", ":")) + "\n"
                )
        summaries[split] = {
            "students": len(members),
            "events": sum(attempts.values()),
            "correct": sum(positives.values()),
            "sequence_sha256": sha256(target),
            "counts": {
                s: {"attempts": attempts[i], "correct": positives[i]}
                for i, s in enumerate(SKILLS)
            },
        }
    report = {
        "archive_url": SOURCE,
        "archive_sha256": ARCHIVE_HASH,
        "member": MEMBER,
        "mapping_sha256": sha256(DATA / "skill_mapping.json"),
        "split_seed": SEED,
        "counts": dict(counts),
        "source_tag_rows": dict(sorted(source_rows.items())),
        "splits": summaries,
    }
    json_write(CACHE / "summary.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument(
        "--publish-summary",
        action="store_true",
        help="update distributed aggregate source and split audit",
    )
    args = parser.parse_args()
    report = prepare(args.archive)
    if args.publish_summary:
        json_write(DATA / "summary.json", report)
    elif report != json_read(DATA / "summary.json"):
        raise SystemExit("Rebuilt data differs from committed data/dkt/summary.json")
    for split, value in report["splits"].items():
        print(split, value["students"], "students", value["events"], "answers")
