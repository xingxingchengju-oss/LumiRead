"""Fetch verified RGB, MPS signals and the recording's factory calibration."""

import argparse
import concurrent.futures
import io
import json
import struct
import time
import zipfile
from pathlib import Path

from .fetch import RemoteZip, fetch, save_stream
from .monitor_panel import panel
from .sources import CACHE


def calibration(asset, directory):
    target = directory / "rgb-calibration.json"
    if target.exists():
        return
    # The VRS description contains a length-prefixed calib_json tag before its
    # sensor payloads. Read the description out of the licensed ZIP by range.
    with zipfile.ZipFile(RemoteZip(asset)) as archive:
        member = next(n for n in archive.namelist() if n.endswith(".vrs"))
        with archive.open(member) as stream:
            header = stream.read(512 * 1024)
    tag = b"calib_json"
    pos = header.index(tag) + len(tag)
    length = struct.unpack_from("<I", header, pos)[0]
    raw = header[pos + 4 : pos + 4 + length]
    if len(raw) != length or not any(
        c["Label"] == "camera-rgb" for c in json.loads(raw)["CameraCalibrations"]
    ):
        raise ValueError("Missing recording-specific RGB camera")
    save_stream(io.BytesIO(raw), target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    assets = json.loads(args.manifest.read_text())["sequences"]

    def get(row):
        seq = row["id"]
        source = assets["recording_" + seq]
        directory = CACHE / "sequences" / seq
        for attempt in range(4):
            try:
                calibration(source["recording_vrs"], directory)
                fetch(seq, source, seq, False)
                print("Ready", seq, row["monitor_group"], flush=True)
                return
            except (OSError, EOFError, ValueError, zipfile.BadZipFile) as exc:
                if attempt == 3:
                    raise RuntimeError(
                        f"{seq} download failed: {type(exc).__name__}"
                    ) from None
                time.sleep(2**attempt)

    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(get, panel()))


if __name__ == "__main__":
    main()
