"""Verify downloaded artifacts, data metadata and cross-device parity without ML dependencies."""

import argparse
import math
from pathlib import Path

from .common import ARTIFACTS, DATA, SKILLS, json_read, sha256
from .inference import WEIGHTS, _bundle, predict_export

REQUIRED = {
    WEIGHTS,
    "dkt.pt",
    "lightgbm.txt",
    "parity.json",
    "metrics.json",
    "training.json",
    "curves.png",
}


def verify(out=ARTIFACTS, require_cuda=False):
    manifest = json_read(out / "checksums.json")
    if set(manifest) != REQUIRED:
        raise ValueError("Unexpected or incomplete artifact inventory")
    for name, digest in manifest.items():
        if sha256(out / name) != digest:
            raise ValueError(f"Artifact SHA-256 mismatch: {name}")
    training = json_read(out / "training.json")
    for name, key in [
        ("summary.json", "data_summary_sha256"),
        ("skill_mapping.json", "mapping_sha256"),
    ]:
        if sha256(DATA / name) != training[key]:
            raise ValueError(f"Dataset metadata SHA-256 mismatch: {name}")
    parity = json_read(out / "parity.json")
    if parity["reference_device"] != training["training_device"]:
        raise ValueError("Inconsistent device provenance")
    if require_cuda and parity["reference_device"] != "cuda":
        raise ValueError("CUDA-trained bundle required")
    if not parity["cases"] or parity["tolerance"] != 1e-4:
        raise ValueError("Invalid parity test vectors")
    weights, version = _bundle(out)
    errors = []
    for case in parity["cases"]:
        actual = predict_export(case["history"], weights)
        for skill in SKILLS:
            p = actual[skill]
            expected = case["reference"][skill]
            if not 0 <= expected <= 1 or not 0 <= p <= 1:
                raise ValueError("Invalid model probability")
            errors.append(abs(p - expected))
    error = max(errors)
    if not math.isfinite(error) or error > parity["tolerance"]:
        raise ValueError(f"Cross-device DKT parity check failed: {error}")
    return {
        "model_version": version,
        "training_device": training["training_device"],
        "reference_hardware": parity["device_name"],
        "inference_device": "cpu",
        "max_abs_error": error,
        "reference_outputs": len(errors),
        "files_verified": len(manifest),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()
    print(verify(args.out, args.require_cuda))
