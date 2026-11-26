"""Retrieve licensed RitW inputs or the two frozen monitor previews."""

import argparse
import hashlib
import http.client
import io
import json
import os
import shutil
import tempfile
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .sources import ARTIFACTS, CACHE, selected


class RemoteZip(io.RawIOBase):
    """Seekable HTTP ranges for large MPS ZIPs. zipfile verifies the member CRC."""

    def __init__(self, asset):
        self.url = asset["download_url"]
        self.size = asset["file_size_bytes"]
        self.pos = 0
        self.start = 0
        self.block = b""

    def seek(self, offset, whence=0):
        self.pos = max(0, (0, self.pos, self.size)[whence] + offset)
        return self.pos

    def tell(self):
        return self.pos

    def seekable(self):
        return True

    def read(self, size=-1):
        end = min(self.size, self.pos + size) if size >= 0 else self.size
        if end <= self.pos:
            return b""
        if not (self.start <= self.pos and end <= self.start + len(self.block)):
            last = min(self.size, max(end, self.pos + 65536)) - 1
            request = urllib.request.Request(
                self.url, headers={"Range": f"bytes={self.pos}-{last}"}
            )
            with urllib.request.urlopen(request, timeout=90) as response:
                if (
                    response.status != 206
                    or response.headers.get("Content-Range")
                    != f"bytes {self.pos}-{last}/{self.size}"
                ):
                    raise ValueError("CDN did not return the requested range")
                self.block = response.read()
            self.start = self.pos
            if len(self.block) != last - self.start + 1:
                raise OSError("Incomplete ZIP range")
        data = self.block[self.pos - self.start : end - self.start]
        self.pos = end
        return data


def save_stream(stream, destination, sha1=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as output:
        temp = Path(output.name)
    try:
        with temp.open("wb") as output:
            shutil.copyfileobj(stream, output, length=4 * 1024 * 1024)
        if sha1:
            with temp.open("rb") as check:
                if hashlib.file_digest(check, "sha1").hexdigest() != sha1:
                    raise OSError("Preview checksum differs from Meta's manifest")
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def fetch(seq, assets, preview_id, preview_only):
    folder = CACHE / "sequences" / seq
    paths = [folder / name for name in ("gaze.csv", "odometry.csv")]
    if not preview_only and not all(p.is_file() for p in paths):
        with zipfile.ZipFile(RemoteZip(assets["mps"])) as archive:
            names = archive.namelist()
            for dest, suffixes in zip(
                paths,
                (
                    (
                        "eye_gaze/personalized_eye_gaze.csv",
                        "eye_gaze/general_eye_gaze.csv",
                    ),
                    ("slam/open_loop_trajectory.csv",),
                ),
            ):
                if dest.exists():
                    continue
                member = next(
                    (n for suffix in suffixes for n in names if n.endswith(suffix)),
                    None,
                )
                if member is None:
                    raise ValueError(f"Required MPS channel missing for {seq}")
                with archive.open(member) as source:
                    save_stream(source, dest)
    if seq == preview_id:
        asset = assets["video_main_rgb"]
        preview = folder / "preview.mp4"
        if preview.is_file() and preview.stat().st_size == asset["file_size_bytes"]:
            with preview.open("rb") as stream:
                if hashlib.file_digest(stream, "sha1").hexdigest() == asset["sha1sum"]:
                    return
        with urllib.request.urlopen(asset["download_url"], timeout=120) as source:
            save_stream(source, preview, asset["sha1sum"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("manifest", type=Path)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument(
        "--preview-only",
        action="store_true",
        help="Get the two authorized classroom videos for the frozen monitor.",
    )
    args = p.parse_args()
    if not args.manifest.is_file():
        p.error("Supply the path to your Project Aria download manifest.")
    assets = json.loads(args.manifest.read_text())["sequences"]
    if args.preview_only:
        selected_ids = [
            r["id"]
            for r in json.loads((ARTIFACTS / "monitor.json").read_text())["clips"]
        ]
        preview_id = None
    else:
        panel = selected()
        preview_id = next(
            r["id"]
            for r in panel
            if r["split"] == "test" and r["group"] == "alternating"
        )
        selected_ids = [r["id"] for r in panel]
    missing = [seq for seq in selected_ids if "recording_" + seq not in assets]
    if missing:
        p.error(
            f"Manifest is missing {len(missing)} Seattle recordings including {missing[0]}."
        )

    def run(seq):
        for attempt in range(4):
            try:
                fetch(
                    seq,
                    assets["recording_" + seq],
                    seq if args.preview_only else preview_id,
                    args.preview_only,
                )
                return seq
            except (
                OSError,
                ValueError,
                http.client.HTTPException,
                zipfile.BadZipFile,
            ) as exc:
                if attempt == 3:
                    raise RuntimeError(
                        f"Official download failed for {seq}: {type(exc).__name__}, {getattr(exc, 'code', '')}. Refresh the Explorer manifest or retry."
                    ) from None
                time.sleep(2**attempt)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for n, seq in enumerate(pool.map(run, selected_ids), 1):
            print(f"{n}/{len(selected_ids)} {seq}", flush=True)


if __name__ == "__main__":
    main()
