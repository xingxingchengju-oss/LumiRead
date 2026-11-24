"""Rebuild exact demonstration excerpts from the pinned, byte-verified public file."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

DIRECTORY = Path(__file__).resolve().parents[1] / "data/clouclip"
COMMIT = "6aaca1616e2a6e852d766bd514560d15094ac9c8"
SHA = "6c99f656ca6a7517b809b06226f2be9739c2e8d63f85cc8b755cff506aa6bbe3"
REPO = "https://github.com/tscnlab/ZaunerEtAl_JVis_2026"
RANGES = {
    "stable": ("稳定阅读", 57565, 57578),
    "near": ("持续偏近及恢复", 56348, 56358),
    "dim": ("持续偏暗及恢复", 56768, 56777),
}


def build():
    content = (DIRECTORY / "Sample_Clouclip.csv").read_bytes()
    if hashlib.sha256(content).hexdigest() != SHA:
        raise ValueError(
            "Original Clouclip file checksum differs from the pinned source"
        )
    lines = content.splitlines(keepends=True)
    parts = {}
    for key, (title, start, end) in RANGES.items():
        raw = b"".join(lines[start - 1 : end])
        rows = list(
            csv.DictReader(
                (lines[0] + raw).decode("utf-8-sig").splitlines(), delimiter="\t"
            )
        )
        parts[key] = {
            "title": title,
            "first_line": start,
            "last_line": end,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "records": [
                {
                    "line": line,
                    "Date": row["Date"],
                    "Dis": int(row["Dis"]),
                    "Lux": int(row["Lux"]),
                }
                for line, row in enumerate(rows, start)
            ],
        }
    return {
        "source": {
            "dataset": "Sample_Clouclip.csv",
            "commit": COMMIT,
            "sha256": SHA,
            "file_url": f"{REPO}/blob/{COMMIT}/data/Sample_Clouclip.csv",
            "supplement": "https://tscnlab.github.io/ZaunerEtAl_JVis_2026/supplement.html",
            "article": "https://doi.org/10.1167/jov.26.7.1",
            "timezone": "America/Chicago",
        },
        "segments": parts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = DIRECTORY / "segments.json"
    result = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if target.read_text() != result:
            raise SystemExit("Clouclip excerpts differ from the original rows.")
        print("Verified 3 contiguous excerpts against all 2,115,103 original bytes.")
    else:
        target.write_text(result)
