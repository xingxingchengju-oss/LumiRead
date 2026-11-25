"""Pinned Seattle annotation sources and deterministic whole-recording sampling."""

import csv
import hashlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache/ritw"
UPSTREAM = CACHE / "upstream"
REVISION = "cb315554cf54927b9ca6056143bca96191afc98d"
ANNOTATIONS = UPSTREAM / "reading_in_the_wild_seattle"
ARTIFACTS = ROOT / "artifacts/ritw"
QUOTAS = {"train": 8, "val": 3, "test": 5}
CLASSES = ("No read", "Print", "Digital", "Object")


def rows(name):
    with (ANNOTATIONS / name).open(newline="") as f:
        return list(csv.DictReader(f))


def selected():
    groups = defaultdict(list)
    for row in rows("ritw_annotations.csv"):
        task = int(row["task"])
        if row["calibration_success"] != "True":
            continue
        if task == 16:
            group = "alternating"
        elif not row["whisper_start"] or not row["whisper_end"]:
            continue
        elif row["reading"] == "False":
            group = "hard_negative" if task in (8, 9, 10) else "everyday"
        else:
            group = row["medium"]
        if group:
            groups[row["split"], group].append(row)
    result = []
    for (split, group), candidates in sorted(groups.items()):
        ranked = sorted(
            candidates,
            key=lambda r: hashlib.sha256(
                ("LumiRead-Seattle-v1/" + r["id"]).encode()
            ).digest(),
        )
        result.extend(dict(r, group=group) for r in ranked[: QUOTAS[split]])
    return result


def showcase_id():
    return next(
        r["id"]
        for r in selected()
        if r["split"] == "test" and r["group"] == "alternating"
    )
