"""One chronological learner per simulated FedAvg client, with held-out validation selection."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path

import lightgbm
import numpy as np
import sklearn
import torch
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from torch.nn import functional as F

from .common import ARTIFACTS, DATA, json_read, json_write, sha256
from .dataset import read_split, tensors
from .evaluate import predict_sequences
from .fed_inference import FEDERATED
from .model import DKT, parity_reference

CPU = torch.device("cpu")
DESIGN = DATA / "federated_protocol.json"


def protocol():
    params = json_read(DESIGN)
    if (
        sha256(DATA / "summary.json") != params["data_summary_sha256"]
        or sha256(ARTIFACTS / "checksums.json")
        != params["frozen_central_manifest_sha256"]
    ):
        raise ValueError(
            "Data or frozen central artifact manifest differs from the registered protocol"
        )
    return params


def valid_targets(client):
    return int((client[2] >= 0).sum().item())


@torch.no_grad()
def add_weighted_state(total, local_state, targets):
    """Accumulate the unnormalized, target-count-weighted parameters in float64."""
    if targets < 1:
        raise ValueError("A client update must contain at least one target")
    for name, value in local_state.items():
        total[name].add_(value, alpha=targets)


def client_step(local, optimizer, data, params):
    x, skills, target = data
    valid = target >= 0
    loss_sum = 0.0
    for _ in range(params["local_epochs"]):
        optimizer.zero_grad()
        logits = local(x).gather(2, skills.unsqueeze(2)).squeeze(2)
        loss = F.binary_cross_entropy_with_logits(logits[valid], target[valid])
        loss.backward()
        torch.nn.utils.clip_grad_norm_(local.parameters(), params["gradient_clip"])
        optimizer.step()
        loss_sum += loss.item()
    return loss_sum / params["local_epochs"]


def run_seed(seed, clients, counts, validation, params, directory):
    rng = np.random.default_rng(seed)
    torch.manual_seed(seed)
    server, local = DKT(), DKT()
    optimizer = torch.optim.SGD(
        local.parameters(), lr=params["learning_rate"], momentum=0
    )
    history, best_round, best_auc = [], 0, -float("inf")
    tensor_bytes = sum(p.numel() * p.element_size() for p in server.parameters())
    for round_n in range(1, params["rounds"] + 1):
        start = time.perf_counter()
        before = server.state_dict()
        total = {k: torch.zeros_like(v, dtype=torch.float64) for k, v in before.items()}
        chosen = rng.choice(
            len(clients), size=params["clients_per_round"], replace=False
        ).tolist()
        target_counts = [counts[i] for i in chosen]
        count = sum(target_counts)
        weighted_loss = 0.0
        for i, target_n in zip(chosen, target_counts, strict=True):
            local.load_state_dict(before)
            loss = client_step(local, optimizer, clients[i], params)
            add_weighted_state(total, local.state_dict(), target_n)
            weighted_loss += loss * target_n
        averaged = {k: (v / count).to(before[k].dtype) for k, v in total.items()}
        norm = (
            sum(float((averaged[k] - v).square().sum()) for k, v in before.items())
            ** 0.5
        )
        server.load_state_dict(averaged)
        labels, _, predicted = predict_sequences(server, validation, CPU)
        auc = float(roc_auc_score(labels, predicted))
        record = {
            "round": round_n,
            "client_count": len(chosen),
            "target_count": count,
            "client_target_min": min(target_counts),
            "client_target_max": max(target_counts),
            "client_target_histogram": dict(sorted(Counter(target_counts).items())),
            "cohort_sha256": hashlib.sha256(
                json.dumps(chosen, separators=(",", ":")).encode()
            ).hexdigest(),
            "train_loss": weighted_loss / count,
            "validation_auc": auc,
            "validation_brier": float(brier_score_loss(labels, predicted)),
            "validation_log_loss": float(log_loss(labels, predicted)),
            "update_l2": norm,
            "elapsed_seconds": time.perf_counter() - start,
            "logical_upload_bytes": len(chosen) * tensor_bytes,
            "logical_download_bytes": len(chosen) * tensor_bytes,
        }
        history.append(record)
        if auc > best_auc:
            best_round, best_auc = round_n, auc
            torch.save(server.state_dict(), directory / f"seed-{seed}.pt")
        if round_n % 10 == 0:
            print(
                f"seed {seed} round {round_n}/{params['rounds']}: validation AUC {auc:.4f}",
                flush=True,
            )
    return {
        "seed": seed,
        "best_round": best_round,
        "best_validation_auc": best_auc,
        "rounds": history,
    }


def select_run(runs):
    return max(runs, key=lambda r: (r["best_validation_auc"], -r["seed"]))


def train(directory):
    from .fed_evaluate import evaluate_checkpoints

    params = protocol()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    train_set, validation = read_split("train"), read_split("validation")
    clients = [tensors([sequence], CPU) for sequence in train_set]
    counts = [valid_targets(client) for client in clients]
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=directory.parent, prefix=".fed-training-"
    ) as tmp:
        stage = Path(tmp)
        runs = [
            run_seed(seed, clients, counts, validation, params, stage)
            for seed in params["seeds"]
        ]
        # Freeze the default before opening the test split or constructing test labels.
        selected = select_run(runs)
        selected_seed = selected["seed"]
        model = DKT()
        model.load_state_dict(
            torch.load(
                stage / f"seed-{selected_seed}.pt",
                map_location="cpu",
                weights_only=True,
            )
        )
        weights = model.export()
        json_write(stage / "cpu_weights.json", weights)
        json_write(stage / "parity.json", parity_reference(model, CPU, weights))
        comparison, all_tests, serving_error = evaluate_checkpoints(
            stage, params, selected_seed
        )
        for run in runs:
            run["test"] = all_tests[str(run["seed"])]["overall"]
            run["test_short_history"] = all_tests[str(run["seed"])]["short_history"]
            run["test_per_skill"] = all_tests[str(run["seed"])]["per_skill"]
            run["test_history_bins"] = all_tests[str(run["seed"])]["history_bins"]
        split = json_read(DATA / "summary.json")["splits"]
        dataset = {"name": "ASSISTments 2009–2010 corrected Skill Builder"}
        for name, entry in split.items():
            dataset[f"{name}_students"] = entry["students"]
            dataset[f"{name}_targets"] = entry["events"]
        selected_info = {
            "seed": selected_seed,
            "round": selected["best_round"],
            "validation_auc": selected["best_validation_auc"],
            "device": "cpu",
            "model_version": "fedavg-dkt-" + sha256(stage / "cpu_weights.json")[:12],
        }
        seed_stats = {
            metric: {
                "mean": float(np.mean([r["test"][metric] for r in runs])),
                "sample_std": float(np.std([r["test"][metric] for r in runs], ddof=1)),
            }
            for metric in (
                "auc",
                "accuracy",
                "f1",
                "precision",
                "recall",
                "brier",
                "log_loss",
            )
        }
        report = {
            "schema_version": 1,
            "status": "complete",
            "method": "FedAvg",
            "dataset": dataset,
            "protocol": params,
            "selected": selected_info,
            "runs": runs,
            "comparison": comparison,
            "three_seed_test_summary": seed_stats,
            "provenance": {
                "dataset_sha256": params["dataset_archive_sha256"],
                "protocol_sha256": sha256(DESIGN),
                "data_summary_sha256": params["data_summary_sha256"],
                "central_weights_sha256": sha256(ARTIFACTS / "cpu_weights.json"),
                "central_manifest_sha256": params["frozen_central_manifest_sha256"],
                "source_url": "https://sites.google.com/site/assistmentsdata/home/2009-2010-assistment-data/skill-builder-data-2009-2010",
                "simulation": params["simulation"],
                "training_device": "cpu",
                "training_hardware": platform.machine(),
                "torch": str(torch.__version__),
                "lightgbm": lightgbm.__version__,
                "sklearn": sklearn.__version__,
                "numpy": np.__version__,
                "python": platform.python_version(),
                "logical_traffic_note": "FP32 model parameters per selected client in each direction. Protocol overhead is excluded. No network was used for the simulation.",
                "test_serving_max_absolute_error": serving_error,
            },
        }
        json_write(stage / "report.json", report)
        # A compact line-oriented log retains each completed round independently of the viewer.
        with (stage / "rounds.jsonl").open("w") as f:
            for run in runs:
                for row in run["rounds"]:
                    f.write(
                        json.dumps({"seed": run["seed"], **row}, separators=(",", ":"))
                        + "\n"
                    )
        shutil.copyfile(DESIGN, stage / "protocol.json")
        json_write(
            stage / "checksums.json",
            {p.name: sha256(p) for p in sorted(stage.iterdir())},
        )
        directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(stage.iterdir(), key=lambda p: p.name == "checksums.json"):
            os.replace(path, directory / path.name)
    print("Frozen validation-selected FedAvg model", selected_info, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=FEDERATED)
    args = parser.parse_args()
    if args.out.resolve() == ARTIFACTS.resolve():
        parser.error(
            "The central release is frozen. Choose a separate federated directory."
        )
    train(args.out)
