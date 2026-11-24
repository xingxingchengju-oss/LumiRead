"""Verify federated release hashes, registered selection, logical counts and CPU reference cases."""

import argparse
import json
import math
from pathlib import Path

from .common import ARTIFACTS, DATA, SKILLS, json_read, sha256
from .fed_inference import FEDERATED, version
from .inference import predict_export


def check(condition, error):
    if not condition:
        raise ValueError(error)


def verify(directory=FEDERATED):
    design = json_read(DATA / "federated_protocol.json")
    files = {
        "protocol.json",
        "cpu_weights.json",
        "parity.json",
        "report.json",
        "rounds.jsonl",
    }
    files.update(f"seed-{seed}.pt" for seed in design["seeds"])
    manifest = json_read(directory / "checksums.json")
    check(set(manifest) == files, "Federated inventory mismatch")
    for name in files:
        check(
            sha256(directory / name) == manifest[name],
            f"Federated artifact hash mismatch: {name}",
        )
    check(
        sha256(DATA / "federated_protocol.json") == manifest["protocol.json"],
        "Registered design changed",
    )
    check(
        sha256(DATA / "summary.json") == design["data_summary_sha256"],
        "Frozen cohort changed",
    )
    central = json_read(ARTIFACTS / "checksums.json")
    check(
        sha256(ARTIFACTS / "checksums.json")
        == design["frozen_central_manifest_sha256"],
        "Central manifest changed",
    )
    for name in ("dkt.pt", "cpu_weights.json", "lightgbm.txt"):
        check(
            sha256(ARTIFACTS / name) == central[name],
            f"Frozen centralized comparator changed: {name}",
        )
    report = json_read(directory / "report.json")
    check(
        report["protocol"] == design
        and report["provenance"]["protocol_sha256"] == manifest["protocol.json"],
        "Protocol provenance mismatch",
    )
    runs = report["runs"]
    check([r["seed"] for r in runs] == design["seeds"], "Missing registered seed")
    aggregate_logs = []
    for run in runs:
        rows = run["rounds"]
        check(
            [x["round"] for x in rows] == list(range(1, design["rounds"] + 1)),
            "Incomplete round log",
        )
        for x in rows:
            hist = x["client_target_histogram"]
            check(
                sum(hist.values()) == x["client_count"] == design["clients_per_round"],
                "Client counts disagree",
            )
            check(
                sum(int(n) * freq for n, freq in hist.items()) == x["target_count"],
                "Target denominator disagrees",
            )
            check(
                min(map(int, hist)) == x["client_target_min"]
                and max(map(int, hist)) == x["client_target_max"],
                "Client range mismatch",
            )
            check(
                x["logical_upload_bytes"] == x["logical_download_bytes"] > 0
                and x["elapsed_seconds"] > 0,
                "Invalid simulation accounting",
            )
            aggregate_logs.append({"seed": run["seed"], **x})
        best = max(rows, key=lambda r: (r["validation_auc"], -r["round"]))
        check(
            (best["round"], best["validation_auc"])
            == (run["best_round"], run["best_validation_auc"]),
            "Round selection mismatch",
        )
    disk_logs = [
        json.loads(line)
        for line in (directory / "rounds.jsonl").read_text().splitlines()
    ]
    check(disk_logs == aggregate_logs, "Round logs disagree")
    best_run = max(runs, key=lambda r: (r["best_validation_auc"], -r["seed"]))
    selected = report["selected"]
    check(
        (selected["seed"], selected["round"], selected["validation_auc"])
        == (best_run["seed"], best_run["best_round"], best_run["best_validation_auc"]),
        "Default seed selection mismatch",
    )
    sample_count = report["dataset"]["test_targets"]
    for result in report["comparison"].values():
        total = result["overall"]
        check(
            total["attempts"]
            == sample_count
            == sum(map(sum, total["confusion_matrix"])),
            "Invalid comparison sample count",
        )
        check(
            sum(v["attempts"] for v in result["per_skill"].values()) == sample_count,
            "Skill group count mismatch",
        )
        bins = result["history_bins"]
        check(
            sum(v["attempts"] for v in bins.values()) == sample_count,
            "History group count mismatch",
        )
        check(
            bins["zero"]["attempts"] + bins["one_to_four"]["attempts"]
            == result["short_history"]["attempts"],
            "Short-history count mismatch",
        )
    weights, model_version = version(directory)
    check(model_version == selected["model_version"], "Selected CPU export mismatch")
    reference = json_read(directory / "parity.json")
    errors = []
    for case in reference["cases"]:
        actual = predict_export(case["history"], weights)
        errors.extend(abs(actual[s] - case["reference"][s]) for s in SKILLS)
    check(
        len(errors) == 30 and all(math.isfinite(x) and x <= 1e-4 for x in errors),
        "Federated CPU parity failed",
    )
    return {
        "model_version": model_version,
        "seeds": len(runs),
        "rounds": len(aggregate_logs),
        "files": len(files),
        "max_reference_error": max(errors),
        "test_targets": sample_count,
        "default_seed": selected["seed"],
        "default_round": selected["round"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=FEDERATED)
    print(verify(parser.parse_args().out))
