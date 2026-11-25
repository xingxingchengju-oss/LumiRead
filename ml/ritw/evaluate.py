"""Compare released RitW models with sequence-disjoint logistic baselines on real MPS signals."""

import argparse
import ast
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .sources import (
    ARTIFACTS,
    CACHE,
    CLASSES,
    QUOTAS,
    REVISION,
    UPSTREAM,
    rows,
    selected,
    showcase_id,
)

ODOM = [f"device_linear_velocity_{k}_odometry" for k in "xyz"] + [
    f"angular_velocity_{k}_device" for k in "xyz"
]


def signals(path, columns):
    with path.open() as f:
        header = next(csv.reader(f))
        use = [header.index(k) for k in ["tracking_timestamp_us", *columns]]
        data = np.genfromtxt(f, delimiter=",", usecols=use, invalid_raise=True)
    if data.ndim != 2 or np.any(np.diff(data[:, 0]) < 0):
        raise ValueError(f"Invalid recording clock in {path.name}")
    return data[:, 0] / 1e6, data[:, 1:]


def annotation(row, mixed):
    if row["group"] == "alternating":
        m = mixed[row["id"]]
        intervals = [
            (float(m[f"start {i}"]), float(m[f"finish {i}"]))
            for i in range(1, 11)
            if m[f"start {i}"] and m[f"finish {i}"]
        ]
        tags = [
            value.lower()
            for _, values in ast.literal_eval(row["tags"])
            for value in values
        ]
        media = {
            name
            for name in CLASSES[1:]
            if any(value.startswith(name.lower()) for value in tags)
        }
        medium = CLASSES.index(media.pop()) if len(media) == 1 else -1
        return float(m["calib"]), float(m["end"]), intervals, medium
    start, end = float(row["whisper_start"]), float(row["whisper_end"])
    if row["reading"] == "True":
        return start, end, [(start, end)], CLASSES.index(row["medium"])
    return start, end, [], 0


def windows(row, mixed):
    folder = CACHE / "sequences" / row["id"]
    gaze_file, head_file = folder / "gaze.csv", folder / "odometry.csv"
    ts, angle = signals(
        gaze_file, ["left_yaw_rads_cpf", "right_yaw_rads_cpf", "pitch_rads_cpf"]
    )
    ht, velocity = signals(head_file, ODOM)
    # Binocular intersection direction in the central pupil frame, as in Meta's preprocessing.
    tangent = np.tan(angle)
    rays = np.column_stack(
        ((tangent[:, 0] + tangent[:, 1]) / 2, tangent[:, 2], np.ones(len(ts)))
    )
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    start, end, intervals, medium = annotation(row, mixed)
    calib = float(
        mixed[row["id"]]["calib"]
        if row["group"] == "alternating"
        else row["calib_time"]
    )
    origin = float(row["calibration_time"]) / 1e6 - calib
    seconds = np.arange(math.ceil(start), math.floor(end), dtype=int)
    last = np.searchsorted(ts, origin + seconds, side="right") - 1
    gi = last[:, None] + np.arange(-120, 1)
    allowed = gi[:, 0] >= 0
    gi = gi.clip(0, len(ts) - 1)
    times = ts[gi]
    hi = np.searchsorted(ht, times[:, 1:], side="right") - 1
    allowed &= (hi[:, 0] >= 0) & (origin + seconds - times[:, -1] < 0.05)
    hi = hi.clip(0, len(ht) - 1)
    steps = np.diff(times, axis=1)
    allowed &= (steps.min(axis=1) > 0) & (steps.max(axis=1) < 0.05)
    allowed &= np.abs(times[:, -1] - times[:, 0] - 2) < 0.1
    allowed &= (times[:, 1:] - ht[hi]).max(axis=1) < 0.05
    gaze = (np.diff(rays[gi], axis=1) * 60).astype("float32")
    head = velocity[hi].astype("float32")
    allowed &= np.isfinite(gaze).all(axis=(1, 2)) & np.isfinite(head).all(axis=(1, 2))
    t = seconds[allowed]
    labels = np.array([any(a <= s < b for a, b in intervals) for s in t], dtype=int)
    truth_seconds = sum(
        np.maximum(0, np.minimum(t + 1, b) - np.maximum(t, a)).sum()
        for a, b in intervals
    )
    return {
        "row": row,
        "t": t,
        "gaze": gaze[allowed],
        "head": head[allowed],
        "y": labels,
        "ym": np.where(labels, medium, 0),
        "start": start,
        "end": end,
        "truth": intervals,
        "truth_seconds": float(truth_seconds),
        "medium": medium,
    }


def official(name):
    sys.path.insert(0, str(UPSTREAM / "models"))
    from model import MultimodalTransformer

    path = UPSTREAM / "models/models" / (name + ".ckpt")
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)["state_dict"]
    state = {
        k.removeprefix("model."): v
        for k, v in checkpoint.items()
        if k.startswith("model.")
    }
    has_rgb = "rgb_encoder.conv1.weight" in state
    model = MultimodalTransformer(
        num_classes=state["fc.weight"].shape[0], input_dim=[3, 6, 3 if has_rgb else 0]
    )
    if not has_rgb:
        # The released four-way checkpoint retains an unused RGB position embedding.
        state.pop("rgb_pe", None)
    model.load_state_dict(state, strict=True)
    return model.eval()


def neural_predict(model, clip):
    with torch.inference_mode():
        batches = [
            model(
                {
                    "gaze": torch.from_numpy(clip["gaze"][i : i + 64]),
                    "odom": torch.from_numpy(clip["head"][i : i + 64]),
                }
            )
            .argmax(1)
            .numpy()
            for i in range(0, len(clip["t"]), 64)
        ]
    return np.concatenate(batches) if batches else np.empty(0, dtype=int)


def summarize(clips, reading, medium):
    y = np.concatenate([c["y"] for c in clips])
    ym = np.concatenate([c["ym"] for c in clips])
    r, m = np.concatenate(reading), np.concatenate(medium)
    known = ym >= 0
    hard = np.concatenate(
        [np.full(len(c["t"]), c["row"]["group"] == "hard_negative") for c in clips]
    )
    return {
        "read_f1": float(f1_score(y, r, zero_division=0)),
        "read_precision": float(precision_score(y, r, zero_division=0)),
        "read_recall": float(recall_score(y, r, zero_division=0)),
        "medium_recall": dict(
            zip(
                CLASSES,
                recall_score(
                    ym[known], m[known], labels=range(4), average=None, zero_division=0
                ).tolist(),
            )
        ),
        "medium_support": dict(
            zip(CLASSES, np.bincount(ym[known], minlength=4).tolist())
        ),
        "duration_mae_seconds": float(
            np.mean(
                [
                    abs(p.sum() - c["truth_seconds"])
                    for c, p in zip(clips, reading)
                    if len(p)
                ]
            )
        ),
        "hard_negative_windows": int(hard.sum()),
        "hard_false_positive_windows": int(r[hard].sum()),
        "hard_false_positive_rate": float(r[hard].mean()),
    }


def baseline(clips, target):
    def split_arrays(split):
        subset = [c for c in clips if c["row"]["split"] == split]
        x = np.concatenate([c["x"] for c in subset])
        y = np.concatenate([c[target] for c in subset])
        return x[y >= 0], y[y >= 0]

    train, y = split_arrays("train")
    valid, vy = split_arrays("val")
    candidates = []
    for strength in (0.1, 1.0, 10.0):
        model = make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=strength, max_iter=500, class_weight="balanced", random_state=6083
            ),
        )
        model.fit(train, y)
        candidates.append(
            (
                f1_score(
                    vy,
                    model.predict(valid),
                    average="binary" if target == "y" else "macro",
                    zero_division=0,
                ),
                strength,
                model,
            )
        )
    return max(candidates, key=lambda item: item[0])


def runs(c, r, m):
    result = []
    for t, binary, medium in zip(c["t"].tolist(), r.tolist(), m.tolist()):
        if result and result[-1][1] == t and result[-1][2:] == [binary, medium]:
            result[-1][1] = t + 1
        else:
            result.append([t, t + 1, binary, medium])
    return result


def channel_hashes(recording):
    folder = CACHE / "sequences" / recording
    digests = {}
    for channel in ("gaze", "odometry"):
        with (folder / (channel + ".csv")).open("rb") as stream:
            digests[channel] = hashlib.file_digest(stream, "sha256").hexdigest()
    return digests


def fitted_parameters(pipeline):
    scaler, classifier = pipeline.steps[0][1], pipeline.steps[1][1]
    return {
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coef": classifier.coef_.tolist(),
        "intercept": classifier.intercept_.tolist(),
        "classes": classifier.classes_.tolist(),
        "C": classifier.C,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    out = parser.parse_args().out
    if (
        subprocess.check_output(
            ["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True
        ).strip()
        != REVISION
    ):
        raise SystemExit("Check out the published Meta revision before evaluating.")
    torch.set_num_threads(3)
    mixed = {r["id"]: r for r in rows("task16_annotations.csv")}
    models = [official("v1_default"), official("v1_medium")]
    clips = []
    for row in selected():
        c = windows(row, mixed)
        if not len(c["t"]):
            raise ValueError("No valid co-observed windows: " + row["id"])
        features = np.concatenate((c["gaze"], c["head"]), axis=2)
        c["x"] = np.column_stack(
            (
                features.mean(1),
                features.std(1),
                np.abs(features).mean(1),
                np.abs(features).max(1),
            )
        )
        if row["split"] == "test":
            c["read"], c["media"] = [neural_predict(model, c) for model in models]
        del c["gaze"], c["head"]
        clips.append(c)
        print(f"{len(clips)}: {row['id']}, {len(c['t'])} seconds", flush=True)
    test = [c for c in clips if c["row"]["split"] == "test"]
    real_r = [c["read"] for c in test]
    real_m = [c["media"] for c in test]
    read_val, read_c, read_model = baseline(clips, "y")
    med_val, med_c, med_model = baseline(clips, "ym")
    base_r = [read_model.predict(c["x"]) for c in test]
    base_m = [med_model.predict(c["x"]) for c in test]
    report = {
        "revision": REVISION,
        "modalities": ["CPF gaze velocity", "MPS six-axis head velocity"],
        "quotas_per_stratum": QUOTAS,
        "splits": {
            s: {
                "recordings": sum(c["row"]["split"] == s for c in clips),
                "seconds": sum(len(c["t"]) for c in clips if c["row"]["split"] == s),
            }
            for s in QUOTAS
        },
        "official": summarize(test, real_r, real_m),
        "logistic": summarize(test, base_r, base_m),
        "selection": {
            "reading_C": read_c,
            "medium_C": med_c,
            "reading_validation_f1": float(read_val),
            "medium_validation_macro_f1": float(med_val),
        },
        "checkpoints": {
            name: hashlib.sha256(
                (UPSTREAM / "models/models" / (name + ".ckpt")).read_bytes()
            ).hexdigest()
            for name in ("v1_default", "v1_medium")
        },
        "inventory": [
            {
                "id": c["row"]["id"],
                "split": c["row"]["split"],
                "group": c["row"]["group"],
                "seconds": len(c["t"]),
                "sha256": channel_hashes(c["row"]["id"]),
            }
            for c in clips
        ],
    }
    replays = []
    for c, br, bm in zip(test, base_r, base_m):
        row = c["row"]
        replays.append(
            {
                "id": row["id"],
                "date": datetime.fromtimestamp(float(row["start_time"]), UTC)
                .date()
                .isoformat(),
                "group": row["group"],
                "evaluation": [c["start"], c["end"]],
                "reference_intervals": c["truth"],
                "reference_medium": c["medium"],
                "covered_seconds": len(c["t"]),
                "reference_read_seconds": c["truth_seconds"],
                "predicted_read_seconds": int(c["read"].sum()),
                "intervals": runs(c, c["read"], c["media"]),
                "baseline_intervals": runs(c, br, bm),
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    baselines = {
        "channels": ["gaze_x", "gaze_y", "gaze_z", *ODOM],
        "summaries": ["mean", "std_ddof0", "mean_abs", "max_abs"],
        "reading": fitted_parameters(read_model),
        "medium": fitted_parameters(med_model),
    }
    for name, data in (
        ("metrics", report),
        ("replays", {"showcase": showcase_id(), "classes": CLASSES, "clips": replays}),
        ("baselines", baselines),
    ):
        (out / (name + ".json")).write_text(
            json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            + "\n"
        )
    print(
        json.dumps({k: report[k] for k in ("splits", "official", "logistic")}, indent=2)
    )


if __name__ == "__main__":
    main()
