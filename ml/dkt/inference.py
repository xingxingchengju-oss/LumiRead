"""Portable CPU inference for the frozen PyTorch LSTM. Uses only Python's standard library."""

import math
import operator
from functools import lru_cache

from .common import ARTIFACTS, SKILLS, json_read, sha256

WEIGHTS = "cpu_weights.json"


class ModelUnavailable(RuntimeError):
    """The expected, verified DKT export could not be loaded."""


@lru_cache(maxsize=2)
def _load(directory, expected, file_signature):
    path = directory / WEIGHTS
    if sha256(path) != expected:
        raise ModelUnavailable("DKT CPU weights failed SHA-256 verification")
    weights = json_read(path)
    if weights.get("schema") != 1 or tuple(weights["skills"]) != SKILLS:
        raise ModelUnavailable("DKT schema or skill order mismatch")
    return weights


def _bundle(directory=ARTIFACTS):
    try:
        expected = json_read(directory / "checksums.json")[WEIGHTS]
        stat = (directory / WEIGHTS).stat()
        signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        return _load(directory, expected, signature), "dkt-lstm-" + expected[:12]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ModelUnavailable(f"DKT export unavailable: {exc}") from exc


def model_info():
    try:
        _, version = _bundle()
        return {"model_version": version, "device": "cpu", "available": True}
    except ModelUnavailable as exc:
        return {
            "model_version": None,
            "device": "cpu",
            "available": False,
            "error": str(exc),
        }


def _sigmoid(value):
    if value < 0:
        exp = math.exp(value)
        return exp / (1.0 + exp)
    return 1.0 / (1.0 + math.exp(-value))


def predict_export(history, weights):
    """BOS predicts the first problem. Each response advances the state exactly once."""
    tokens = [0]
    for skill, correct in history:
        if skill not in SKILLS or type(correct) is not bool:
            raise ValueError(
                "Expected a known skill_id and a boolean correctness value"
            )
        tokens.append(1 + 2 * SKILLS.index(skill) + int(correct))
    n = weights["hidden"]
    h, c = [0.0] * n, [0.0] * n
    for token in tokens:
        inputs = weights["token_gate"][token]
        gates = [
            bias + sum(map(operator.mul, row, h))
            for bias, row in zip(inputs, weights["hh"])
        ]
        for j in range(n):
            c[j] = _sigmoid(gates[n + j]) * c[j] + _sigmoid(gates[j]) * math.tanh(
                gates[2 * n + j]
            )
            h[j] = _sigmoid(gates[3 * n + j]) * math.tanh(c[j])
    return {
        s: _sigmoid(b + sum(map(operator.mul, row, h)))
        for s, b, row in zip(SKILLS, weights["out_bias"], weights["out_weight"])
    }


def predict(history: list[tuple[str, bool]]) -> dict[str, float]:
    return predict_export(history, _bundle()[0])
