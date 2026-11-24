"""Train, select on validation AUC, export, and evaluate once on held-out students."""

import argparse
import copy
import os
import platform
import random
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import lightgbm
import matplotlib
import numpy as np
import sklearn
import torch
from sklearn.metrics import log_loss, roc_auc_score, roc_curve
from torch.nn import functional as F

from ml.baselines import lightgbm as baseline

from .common import ARTIFACTS, DATA, SEED, SKILLS, json_write, sha256
from .dataset import batches, read_split, tensors
from .evaluate import evaluate, predict_sequences
from .inference import WEIGHTS
from .model import DKT, EMBEDDING, HIDDEN, parity_reference


def fit(train_set, val_set, device, epochs, patience):
    model = DKT().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    rng = np.random.default_rng(SEED)
    history, best_state, best_epoch, best_auc = [], None, 0, float("-inf")
    for epoch in range(1, epochs + 1):
        model.train()
        loss_sum, count = 0, 0
        for seqs in batches(train_set, 64, rng):
            x, skills, targets = tensors(seqs, device)
            mask = targets >= 0
            optimizer.zero_grad()
            logits = model(x).gather(2, skills.unsqueeze(2)).squeeze(2)
            loss = F.binary_cross_entropy_with_logits(logits[mask], targets[mask])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            n = int(mask.sum().item())
            loss_sum += loss.item() * n
            count += n
        y, _, pred = predict_sequences(model, val_set, device)
        auc = float(roc_auc_score(y, pred))
        history.append(
            {
                "epoch": epoch,
                "train_loss": loss_sum / count,
                "validation_loss": float(log_loss(y, pred)),
                "validation_auc": auc,
            }
        )
        print(
            f"epoch {epoch:2}  loss {loss_sum / count:.5f}  val AUC {auc:.5f}",
            flush=True,
        )
        if auc > best_auc:
            best_state = copy.deepcopy(model.state_dict())
            best_epoch, best_auc = epoch, auc
        elif epoch - best_epoch >= patience:
            break
    model.load_state_dict(best_state)
    return model, history, best_epoch


def plot(history, best_epoch, y, predictions, out):
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.5), layout="constrained")
    epoch = [x["epoch"] for x in history]
    for column, label in [("train_loss", "Train"), ("validation_loss", "Validation")]:
        axes[0].plot(epoch, [x[column] for x in history], label=label)
    axes[0].legend()
    axes[0].set(xlabel="Epoch", ylabel="Binary cross-entropy", title="DKT training")
    axes[1].plot(epoch, [x["validation_auc"] for x in history], color="#215d47")
    axes[1].axvline(best_epoch, color="#888", ls="--", label="Selected epoch")
    axes[1].legend()
    axes[1].set(
        xlabel="Epoch", ylabel="Validation ROC AUC", title="Checkpoint selection"
    )
    axes[2].plot([0, 1], [0, 1], color="#888", ls=":")
    for name, p in predictions.items():
        fpr, tpr, _ = roc_curve(y, p)
        axes[2].plot(fpr, tpr, label=f"{name.upper()} {roc_auc_score(y, p):.3f}")
    axes[2].legend(loc="lower right")
    axes[2].set(
        xlabel="False positive rate",
        ylabel="True positive rate",
        title="Held-out learners",
    )
    fig.savefig(out / "curves.png", dpi=160)
    plt.close(fig)


def train(out, device, epochs=35, patience=6):
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("Requested CUDA is unavailable")
    out.mkdir(parents=True, exist_ok=True)
    train_set, val_set = read_split("train"), read_split("validation")
    model, history, best_epoch = fit(train_set, val_set, device, epochs, patience)
    exported = model.export()
    json_write(out / WEIGHTS, exported)
    parity = parity_reference(model, device, exported)
    json_write(out / "parity.json", parity)
    torch.save({k: v.cpu() for k, v in model.state_dict().items()}, out / "dkt.pt")
    baseline_run = baseline.train(train_set, val_set, out / "lightgbm.txt")
    test, y, outputs = evaluate(out)
    run = {
        "seed": SEED,
        "max_epochs": epochs,
        "patience": patience,
        "best_epoch": best_epoch,
        "batch_size": 64,
        "optimizer": "Adam",
        "learning_rate": 0.003,
        "gradient_clip": 5,
        "selection": "highest validation ROC AUC",
        "hidden": HIDDEN,
        "embedding": EMBEDDING,
        "skills": list(SKILLS),
        "training_device": str(device),
        "training_hardware": (
            torch.cuda.get_device_name(device)
            if device.type == "cuda"
            else platform.machine()
        ),
        "inference_device": "cpu",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": str(torch.__version__),
        "cuda": torch.version.cuda,
        "numpy": np.__version__,
        "lightgbm": lightgbm.__version__,
        "sklearn": sklearn.__version__,
        "matplotlib": matplotlib.__version__,
        "data_summary_sha256": sha256(DATA / "summary.json"),
        "mapping_sha256": sha256(DATA / "skill_mapping.json"),
    }
    json_write(
        out / "metrics.json",
        {
            "threshold": 0.5,
            "positive_label": 1,
            "confusion_axes": "rows=true, columns=predicted, labels=[0,1]",
            "test": test,
        },
    )
    json_write(
        out / "training.json", {**run, "epochs": history, "baseline": baseline_run}
    )
    plot(history, best_epoch, y, outputs, out)
    files = [
        WEIGHTS,
        "dkt.pt",
        "lightgbm.txt",
        "parity.json",
        "metrics.json",
        "training.json",
        "curves.png",
    ]
    json_write(out / "checksums.json", {name: sha256(out / name) for name in files})
    for name, values in test.items():
        print(name, values["overall"], flush=True)
    print(
        "Training-device vs. CPU export max abs error:", parity["export_max_abs_error"]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=ARTIFACTS, type=Path)
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--epochs", default=35, type=int)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error("--epochs must be positive")
    train(args.out, torch.device(args.device), args.epochs)
