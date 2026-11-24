"""Train-time implementation. The app imports only ml.dkt.inference."""

import torch
from torch import nn

from .common import SKILLS
from .inference import predict_export

HIDDEN = 24
EMBEDDING = 12
REFERENCE_HISTORIES = [
    [],
    [("mixed_arithmetic", False)],
    [("mixed_arithmetic", True)],
    [(s, j % 2 == 0) for j, s in enumerate(SKILLS)],
    [(s, j % 3 == 0) for j in range(12) for s in reversed(SKILLS)],
]


class DKT(nn.Module):
    def __init__(self):
        super().__init__()
        self.embedding = nn.Embedding(1 + 2 * len(SKILLS), EMBEDDING)
        self.lstm = nn.LSTM(EMBEDDING, HIDDEN, batch_first=True)
        self.head = nn.Linear(HIDDEN, len(SKILLS))

    def forward(self, inputs):
        hidden, _ = self.lstm(self.embedding(inputs))
        return self.head(hidden)

    def export(self):
        # PyTorch orders LSTM gates input, forget, candidate, output.
        weights = {k: v.detach().cpu() for k, v in self.state_dict().items()}
        gates = (
            weights["embedding.weight"] @ weights["lstm.weight_ih_l0"].T
            + weights["lstm.bias_ih_l0"]
            + weights["lstm.bias_hh_l0"]
        )
        return {
            "schema": 1,
            "skills": list(SKILLS),
            "hidden": HIDDEN,
            "token_gate": gates.tolist(),
            "hh": weights["lstm.weight_hh_l0"].tolist(),
            "out_weight": weights["head.weight"].tolist(),
            "out_bias": weights["head.bias"].tolist(),
        }


@torch.no_grad()
def parity_reference(model, device, exported):
    model.eval()
    cases, max_error = [], 0.0
    for history in REFERENCE_HISTORIES:
        tokens = [0] + [1 + 2 * SKILLS.index(s) + int(c) for s, c in history]
        logits = model(torch.tensor([tokens], device=device))[0, -1]
        expected = dict(zip(SKILLS, logits.sigmoid().cpu().tolist()))
        actual = predict_export(history, exported)
        max_error = max(max_error, max(abs(expected[s] - actual[s]) for s in SKILLS))
        cases.append({"history": history, "reference": expected})
    if max_error > 1e-4:
        raise ValueError(
            f"Portable inference differs from the training device by {max_error}"
        )
    return {
        "reference_device": str(device),
        "device_name": torch.cuda.get_device_name(device)
        if device.type == "cuda"
        else "CPU",
        "tolerance": 1e-4,
        "export_max_abs_error": max_error,
        "cases": cases,
    }
