"""Standard-library CPU inference for the validation-selected federated model."""

from .common import ROOT
from .inference import ModelUnavailable, _bundle, predict_export

FEDERATED = ROOT / "artifacts/federated"


def version(directory=FEDERATED):
    weights, central_style_version = _bundle(directory)
    return weights, central_style_version.replace("dkt-lstm-", "fedavg-dkt-", 1)


def predict(history: list[tuple[str, bool]]) -> dict[str, float]:
    return predict_export(history, version()[0])


def model_info():
    try:
        _, model_version = version()
        return {"available": True, "model_version": model_version, "device": "cpu"}
    except ModelUnavailable as exc:
        return {
            "available": False,
            "model_version": None,
            "device": "cpu",
            "error": str(exc),
        }
