"""Files, skill ordering and reproducibility constants shared with CPU inference."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/dkt"
CACHE = ROOT / ".cache/dkt"
ARTIFACTS = ROOT / "artifacts/dkt"
SKILLS = (
    "mixed_arithmetic",
    "fractions",
    "decimals",
    "equations",
    "area",
    "word_modeling",
)
SEED = 6083
SPLITS = ("train", "validation", "test")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def json_write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )


def json_read(path):
    return json.loads(Path(path).read_text())
