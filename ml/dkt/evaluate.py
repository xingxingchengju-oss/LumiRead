"""Repeat evaluation of both saved models against the identical held-out learners."""

import argparse

import lightgbm as lgb
import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    roc_auc_score,
)

from ml.baselines.lightgbm import features

from .common import ARTIFACTS, SKILLS, json_read
from .dataset import batches, read_split, tensors
from .inference import _bundle, predict_export
from .model import DKT


@torch.no_grad()
def predict_sequences(model, seqs, device):
    model.eval()
    labels, skills, scores = [], [], []
    for seq in batches(seqs, 64):
        x, skill, target = tensors(seq, device)
        valid = target >= 0
        raw = model(x).gather(2, skill.unsqueeze(2)).squeeze(2)
        labels.extend(target[valid].cpu().tolist())
        skills.extend(skill[valid].cpu().tolist())
        scores.extend(raw[valid].sigmoid().cpu().tolist())
    return np.asarray(labels, dtype=int), np.asarray(skills), np.asarray(scores)


def metrics(y, p):
    decision = p >= 0.5
    return {
        "attempts": len(y),
        "correct": int(y.sum()),
        "auc": float(roc_auc_score(y, p)),
        "accuracy": float(accuracy_score(y, decision)),
        "f1": float(f1_score(y, decision)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "confusion_matrix": confusion_matrix(y, decision, labels=[0, 1]).tolist(),
    }


def evaluate(out, split="test"):
    seqs = read_split(split)
    model = DKT()
    model.load_state_dict(
        torch.load(out / "dkt.pt", weights_only=True, map_location="cpu")
    )
    y, s, p = predict_sequences(model, seqs, torch.device("cpu"))
    x, baseline_y, baseline_s = features(seqs)
    if not (np.array_equal(y, baseline_y) and np.array_equal(s, baseline_s)):
        raise AssertionError("Baseline and DKT target order differs")
    booster = lgb.Booster(model_file=str(out / "lightgbm.txt"))
    outputs = {"dkt": p, "lightgbm": booster.predict(x, num_threads=2)}
    result = {
        name: {
            "overall": metrics(y, scores),
            "per_skill": {
                key: metrics(y[s == i], scores[s == i]) for i, key in enumerate(SKILLS)
            },
        }
        for name, scores in outputs.items()
    }
    return result, y, outputs


def verify_serving(out, expected):
    """Replay the actual deployed CPU predictor before every held-out response."""
    weights, _ = _bundle(out)
    probabilities = []
    for events in read_split("test"):
        history = []
        for skill_index, correct in events:
            skill = SKILLS[skill_index]
            probabilities.append(predict_export(history, weights)[skill])
            history.append((skill, bool(correct)))
    difference = float(np.max(np.abs(np.asarray(probabilities) - expected)))
    if not np.isfinite(difference) or difference > 1e-4:
        raise AssertionError(f"Held-out serving predictions diverge: {difference}")
    return difference


def assert_same(expected, actual):
    for name in actual:
        for key in ["overall", *SKILLS]:
            left = (
                expected[name]["overall"]
                if key == "overall"
                else expected[name]["per_skill"][key]
            )
            right = (
                actual[name]["overall"]
                if key == "overall"
                else actual[name]["per_skill"][key]
            )
            for metric, value in right.items():
                if metric in ("auc", "log_loss"):
                    # CPU kernels may differ slightly across torch builds and platforms.
                    ok = abs(value - left[metric]) < 1e-5
                else:
                    ok = value == left[metric]
                if not ok:
                    raise ValueError(
                        f"{name}/{key}/{metric}: {value!r} != {left[metric]!r}"
                    )


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=ARTIFACTS, type=Path)
    parser.add_argument(
        "--check-serving",
        action="store_true",
        help="also replay every held-out prefix through the deployed CPU runtime",
    )
    args = parser.parse_args()
    torch.set_num_threads(2)
    result, _, outputs = evaluate(args.out)
    assert_same(json_read(args.out / "metrics.json")["test"], result)
    for name in result:
        print(name, result[name]["overall"])
    if args.check_serving:
        print(
            "Held-out serving vs CPU PyTorch maximum absolute error:",
            verify_serving(args.out, outputs["dkt"]),
        )
