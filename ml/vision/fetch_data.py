"""Download public inputs only, checking publisher hashes and avoiding partial artifacts."""

import argparse
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".cache/vision"
ZENODO = "https://zenodo-rdm.web.cern.ch/records/20657011/files/"
LUX_TABLES = {
    "lux-features.csv": (
        "feature_master_latest.csv",
        "a8bd4c1d7451f6d19acba350563c7178",
    ),
    "lux-annotations.csv": (
        "annotation_master_latest.csv",
        "773a87e7b7b1395f5695d9c9ed513180",
    ),
}


def fetch(name, url, expected, algorithm):
    target = CACHE / name

    def matches(file):
        return (
            file.exists()
            and hashlib.new(algorithm, file.read_bytes()).hexdigest() == expected
        )

    if matches(target):
        return
    temp = target.with_suffix(target.suffix + ".partial")
    original = ROOT / "data/vision/original" / name
    if matches(original):
        shutil.copyfile(original, temp)
    else:
        with urllib.request.urlopen(url, timeout=90) as source, temp.open("wb") as dest:
            shutil.copyfileobj(source, dest)
    if not matches(temp):
        raise ValueError(f"Checksum mismatch for {name}")
    temp.replace(target)


if __name__ == "__main__":
    args = argparse.ArgumentParser()
    args.add_argument("dataset", choices=["lux", "gesture"])
    dataset = args.parse_args().dataset
    CACHE.mkdir(parents=True, exist_ok=True)
    if dataset == "lux":
        for name, (remote, checksum) in LUX_TABLES.items():
            fetch(name, ZENODO + remote, checksum, "md5")
    else:
        for row in json.loads(
            (ROOT / "data/vision/gesture-recordings.json").read_text()
        ):
            fetch(row["file"], row["url"], row["sha256"], "sha256")
