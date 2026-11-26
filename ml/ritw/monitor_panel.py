"""Whole-recording validation candidates and held-out controls for the RGB monitor."""

import ast
import hashlib
from itertools import pairwise

from .sources import rows


def reading_intervals(row):
    return [
        (float(row[f"start {i}"]), float(row[f"finish {i}"]))
        for i in range(1, 11)
        if row[f"start {i}"] and row[f"finish {i}"]
    ]


def panel():
    annotations = rows("ritw_annotations.csv")
    mixed = {r["id"]: r for r in rows("task16_annotations.csv")}
    records = []
    for r in annotations:
        if (
            r["split"] != "val"
            or r["task"] != "16"
            or r["calibration_success"] != "True"
        ):
            continue
        tags = {
            v.split()[0] for _, values in ast.literal_eval(r["tags"]) for v in values
        }
        if tags not in ({"Print"}, {"Digital"}) or r["id"] not in mixed:
            continue
        spans = reading_intervals(mixed[r["id"]])
        if not any(c - b >= 12 for (_, b), (c, _) in pairwise(spans)):
            continue
        if max(b - a for a, b in spans) >= 7:
            kind = "paper" if tags == {"Print"} else "digital"
            records.append(dict(r, group="alternating", monitor_group=kind))

    test = [
        r
        for r in annotations
        if r["split"] == "test"
        and r["calibration_success"] == "True"
        and r["whisper_start"]
        and r["whisper_end"]
    ]
    for r in test:
        if r["mode"] == "Videos":
            records.append(dict(r, group=r["medium"], monitor_group="video"))
    controls = {
        "phone": lambda r: (
            r["device"] == "Phone"
            and r["material"] in {"News", "E-Book", "Wikipedia", "Blogpost", "Email"}
        ),
        "computer": lambda r: (
            r["device"] in {"Laptop", "Desktop", "Computer Monitor"}
            and r["reading"] == "True"
        ),
        "paper": lambda r: r["medium"] == "Print" and r["mode"] == "Engaged reading",
        "other_text": lambda r: r["medium"] == "Object" and r["reading"] == "True",
        "rest": lambda r: r["task"] == "11" and r["reading"] == "False",
    }
    for name, matches in controls.items():
        pool = [r for r in test if r["mode"] != "Videos" and matches(r)]
        r = min(
            pool,
            key=lambda r: hashlib.sha256(
                ("LumiRead-monitor-v1/" + r["id"]).encode()
            ).digest(),
        )
        records.append(dict(r, group=r["medium"] or "everyday", monitor_group=name))
    return sorted(records, key=lambda r: (r["split"] != "val", r["id"]))
