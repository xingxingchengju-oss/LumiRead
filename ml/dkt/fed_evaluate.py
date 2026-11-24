"""Independently score the frozen central models and all validation-selected FedAvg seeds."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import lightgbm
import numpy as np
import torch
from sklearn.metrics import (
    brier_score_loss,
    confusion_matrix,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from .common import ARTIFACTS, SKILLS, json_read
from .dataset import read_split
from .evaluate import evaluate as central_scores
from .evaluate import predict_sequences
from .fed_inference import FEDERATED
from .fed_verify import verify
from .inference import predict_export
from .model import DKT


def metrics(y, p):
    decision = p >= 0.5
    confusion = confusion_matrix(y, decision, labels=[0, 1])
    _tn, fp, fn, tp = confusion.ravel()
    return {
        "attempts": len(y),
        "correct": int(y.sum()),
        "auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
        "accuracy": float(np.mean(y == decision)),
        "f1": float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else 0.0,
        "precision": float(precision_score(y, decision, zero_division=0)),
        "recall": float(recall_score(y, decision, zero_division=0)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "confusion_matrix": confusion.tolist(),
    }


def slices(y, p, skills, prior, design):
    def on(mask):
        return metrics(y[mask], p[mask])

    hist = {}
    for name, (low, high) in design["history_bins"].items():
        mask = prior >= low
        if high is not None:
            mask &= prior <= high
        hist[name] = on(mask)
    return {
        "overall": metrics(y, p),
        "short_history": on(prior <= design["short_history_max_prior"]),
        "per_skill": {s: on(skills == i) for i, s in enumerate(SKILLS)},
        "history_bins": hist,
    }


def evaluate_checkpoints(directory, design, selected_seed):
    sequences = read_split("test")
    _, y, central = central_scores(ARTIFACTS)
    labels = np.asarray([c for seq in sequences for _, c in seq])
    skills = np.asarray([s for seq in sequences for s, _ in seq])
    prior = np.asarray([n for seq in sequences for n in range(len(seq))])
    if not np.array_equal(y, labels):
        raise ValueError("Target order mismatch between models")
    all_tests = {}
    default_scores = None
    for seed in design["seeds"]:
        model = DKT()
        model.load_state_dict(
            torch.load(
                directory / f"seed-{seed}.pt", map_location="cpu", weights_only=True
            )
        )
        target, skill, p = predict_sequences(model, sequences, torch.device("cpu"))
        if not np.array_equal(target, labels) or not np.array_equal(skill, skills):
            raise ValueError(
                "Federated target order differs from the frozen test cohort"
            )
        all_tests[str(seed)] = slices(y, p, skills, prior, design)
        if seed == selected_seed:
            default_scores = p
    comparison = {
        "central_dkt": slices(y, central["dkt"], skills, prior, design),
        "federated_dkt": all_tests[str(selected_seed)],
        "lightgbm": slices(y, central["lightgbm"], skills, prior, design),
    }
    portable = json_read(directory / "cpu_weights.json")
    probabilities = []
    for seq in sequences:
        history = []
        for s, c in seq:
            probabilities.append(predict_export(history, portable)[SKILLS[s]])
            history.append((SKILLS[s], bool(c)))
    err = float(np.max(np.abs(np.asarray(probabilities) - default_scores)))
    if not np.isfinite(err) or err > 1e-4:
        raise ValueError(f"Federated deployment parity error: {err}")
    return comparison, all_tests, err


def verify_cohorts(report):
    """Replay public PRNG decisions against the private train split; no held-out student is a client."""
    counts = [len(seq) for seq in read_split("train")]
    client_count = report["protocol"]["clients_per_round"]
    for run in report["runs"]:
        rng = np.random.default_rng(run["seed"])
        for row in run["rounds"]:
            chosen = rng.choice(len(counts), size=client_count, replace=False).tolist()
            actual = Counter(counts[i] for i in chosen)
            digest = hashlib.sha256(
                json.dumps(chosen, separators=(",", ":")).encode()
            ).hexdigest()
            if (
                row["cohort_sha256"] != digest
                or {str(n): freq for n, freq in actual.items()}
                != row["client_target_histogram"]
            ):
                raise ValueError(
                    f"Client selection or aggregation denominator mismatch in seed {run['seed']}, round {row['round']}"
                )


def check_numeric(a, b, path="metrics"):
    if isinstance(a, dict):
        if a.keys() != b.keys():
            raise ValueError(f"{path}: keys differ")
        for k in a:
            check_numeric(a[k], b[k], f"{path}/{k}")
    elif isinstance(a, float):
        if not np.isclose(a, b, atol=1e-5, rtol=0):
            raise ValueError(f"{path}: {a} vs {b}")
    elif a != b:
        raise ValueError(f"{path}: {a} vs {b}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=FEDERATED)
    args = parser.parse_args()
    print(
        f"CPU evaluation with PyTorch {torch.__version__} and LightGBM {lightgbm.__version__}",
        flush=True,
    )
    torch.set_num_threads(1)
    verify(args.out)
    report = json_read(args.out / "report.json")
    verify_cohorts(report)
    comparison, all_tests, error = evaluate_checkpoints(
        args.out, report["protocol"], report["selected"]["seed"]
    )
    check_numeric(comparison, report["comparison"])
    for r in report["runs"]:
        check_numeric(r["test"], all_tests[str(r["seed"])]["overall"])
        check_numeric(
            r["test_short_history"], all_tests[str(r["seed"])]["short_history"]
        )
        check_numeric(r["test_per_skill"], all_tests[str(r["seed"])]["per_skill"])
        check_numeric(r["test_history_bins"], all_tests[str(r["seed"])]["history_bins"])
    for k, v in comparison.items():
        print(k, v["overall"])
    print("Test replay verified; maximum CPU export error", error)
