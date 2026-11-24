"""Classify real meter readings on white paper with two fitted image-luma cutoffs."""

import argparse
import csv
import hashlib
import json
from collections import Counter

from fetch_data import CACHE, LUX_TABLES, ROOT

DATA = ROOT / "data/vision"
CLASSES = ["<300 lx", "300–<500 lx", "≥500 lx"]


def prepare():
    for file, (_, md5) in LUX_TABLES.items():
        if hashlib.md5((CACHE / file).read_bytes()).hexdigest() != md5:
            raise ValueError("Source checksum mismatch. Run fetch_data.py lux.")

    def rows(file):
        with (CACHE / file).open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    annotations = {r["image_path"]: r for r in rows("lux-annotations.csv")}
    output = []
    for feat in rows("lux-features.csv"):
        truth = annotations[feat["image_path"]]
        if truth["surface_group_norm"] != "white_paper":
            continue
        assert float(truth["lux_C"]) == float(feat["lux_C"])
        output.append(
            (
                truth["filename"],
                truth["family_group"],
                float(truth["lux_C"]),
                float(feat["square_mean_luma"]),
            )
        )
    assert len(output) == len({r[0] for r in output}) == 1563
    with (DATA / "lux-white-paper.csv").open("w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["filename", "scene_family", "central_lux", "square_mean_luma"])
        writer.writerows(sorted(output))


def fit(train):
    # Maximize training balanced accuracy. The two integer thresholds are the only fitted parameters.
    prefix = [[0] * 257 for _ in range(3)]
    for row in train:
        prefix[row["label"]][int(row["luma"]) + 1] += 1
    for bins in prefix:
        for i in range(1, len(bins)):
            bins[i] += bins[i - 1]
        if not bins[-1]:
            raise ValueError("Training fold is missing a class")
    best, cutoffs = -1, (0, 0)
    for low in range(1, 255):
        for high in range(low + 1, 256):
            score = (
                prefix[0][low] / prefix[0][-1]
                + (prefix[1][high] - prefix[1][low]) / prefix[1][-1]
                + (prefix[2][-1] - prefix[2][high]) / prefix[2][-1]
            )
            if score > best:
                best, cutoffs = score, (low, high)
    return cutoffs


def metrics(matrix):
    counts = [sum(row) for row in matrix]
    f1 = [
        2 * matrix[i][i] / (counts[i] + sum(row[i] for row in matrix)) for i in range(3)
    ]
    return {
        "n": sum(counts),
        "class_counts": counts,
        "accuracy": sum(matrix[i][i] for i in range(3)) / sum(counts),
        "macro_f1": sum(f1) / 3,
        "confusion_matrix": matrix,
    }


def evaluate():
    with (DATA / "lux-white-paper.csv").open() as handle:
        rows = [
            {
                "scene": r["scene_family"],
                "luma": float(r["square_mean_luma"]),
                "label": sum(float(r["central_lux"]) >= v for v in (300, 500)),
            }
            for r in csv.DictReader(handle)
        ]
    total = [[0] * 3 for _ in range(3)]
    folds = []
    for scene in sorted({r["scene"] for r in rows}):
        train = [r for r in rows if r["scene"] != scene]
        held = [r for r in rows if r["scene"] == scene]
        cuts = fit(train)
        matrix = [[0] * 3 for _ in range(3)]
        for row in held:
            predicted = sum(row["luma"] >= t for t in cuts)
            matrix[row["label"]][predicted] += 1
        assert all(sum(r) > 0 for r in matrix)
        folds.append(
            {
                "held_out_scene_family": scene,
                "train_n": len(train),
                "train_class_counts": [
                    Counter(r["label"] for r in train)[i] for i in range(3)
                ],
                "luma_cutoffs": cuts,
                **metrics(matrix),
            }
        )
        for i in range(3):
            for j in range(3):
                total[i][j] += matrix[i][j]
    report = {
        "source": "10.5281/zenodo.20657011",
        "device": "Samsung Galaxy A16, ISO 50, 1/50 s, WB 4000 K",
        "meter": "Lutron LX-101A",
        "feature": "square_mean_luma",
        "classes": CLASSES,
        "split": "leave one complete scene family out",
        "row_order": "true",
        "column_order": "predicted",
        "folds": folds,
        **metrics(total),
    }
    (DATA / "lux-results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(metrics(total), ensure_ascii=False))


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("--prepare", action="store_true")
    if args.parse_args().prepare:
        prepare()
    evaluate()
