"""Prepare source-clock votes and time-ordered RGB/gaze contact sheets offline."""

import argparse
import hashlib
import json
import math
import os

import av
import numpy as np
import torch
from PIL import Image, ImageDraw
from projectaria_tools.core import calibration

from apps.api.monitor import vote_patches

from .evaluate import neural_predict, official, signals, windows
from .monitor_panel import panel
from .sources import CACHE, UPSTREAM, rows

WORK = CACHE / "monitor-v1"
TILE = 380


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        + "\n"
    )
    os.replace(temp, path)


class GazeProjection:
    def __init__(self, directory, origin, width, height):
        self.ts, self.gaze = signals(
            directory / "gaze.csv",
            ["left_yaw_rads_cpf", "right_yaw_rads_cpf", "pitch_rads_cpf", "depth_m"],
        )
        self.origin = origin
        device = calibration.device_calibration_from_json_string(
            (directory / "rgb-calibration.json").read_text()
        )
        self.camera = calibration.rescale_camera_calibration(
            device.get_camera_calib("camera-rgb"),
            [height, width],
            device.get_device_version(),
            "camera-rgb",
        )
        self.extrinsics = (
            device.get_transform_cpf_sensor("camera-rgb", False).inverse().to_matrix()
        )
        self.width, self.height = width, height

    def at(self, second):
        target = self.origin + second
        i = int(np.searchsorted(self.ts, target))
        candidates = [j for j in (i - 1, i) if 0 <= j < len(self.ts)]
        if not candidates:
            return None
        j = min(candidates, key=lambda k: abs(self.ts[k] - target))
        left, right, pitch, depth = self.gaze[j]
        if (
            abs(self.ts[j] - target) > 0.05
            or not np.isfinite(self.gaze[j]).all()
            or depth <= 0
        ):
            return None
        ray = np.array([(np.tan(left) + np.tan(right)) / 2, np.tan(pitch), 1.0])
        camera_point = self.extrinsics @ np.append(ray * depth / np.linalg.norm(ray), 1)
        xy = self.camera.project(camera_point[:3])
        if xy is None:
            return None
        # Seattle's preview already encodes the raw sensor rotated clockwise.
        point = [(self.width - 1 - xy[1]) / self.width, xy[0] / self.height]
        return (
            [round(float(v), 5) for v in point]
            if all(0 <= v < 1 for v in point)
            else None
        )


def make_sheet(container, stream, projection, patch, directory):
    a, b = patch["start"], patch["end"]
    # Locate the burst around the middle valid second, wholly inside this patch.
    valid = [t for t in range(a, b) if t not in patch["missing"]]
    if not valid:
        return None
    length = min(1.8, b - a - 0.1)
    first = min(
        max(a + 0.03, valid[len(valid) // 2] + 0.5 - length / 2), b - length - 0.05
    )
    targets = np.linspace(first, first + length, 4)
    container.seek(int(first / stream.time_base), stream=stream)
    frames = []
    sheet = Image.new("RGB", (TILE * 2, TILE * 2))
    for frame in container.decode(stream):
        t = frame.time
        if t is None or t < targets[len(frames)]:
            continue
        if t >= b or t - targets[len(frames)] > 0.10:
            break
        dot = projection.at(t) if int(t) in valid else None
        image = frame.to_image().resize((TILE, TILE), Image.Resampling.LANCZOS)
        if dot:
            x, y = dot[0] * TILE, dot[1] * TILE
            draw = ImageDraw.Draw(image)
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline="black", width=4)
            draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline="#00ffaf", width=2)
        index = len(frames)
        sheet.paste(image, (index % 2 * TILE, index // 2 * TILE))
        frames.append({"second": round(t, 4), "gaze": dot})
        if len(frames) == len(targets):
            break
    if not frames:
        return None
    path = directory / f"{a}.jpg"
    sheet.save(path, quality=86)
    return {"frames": frames, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def prepare(row, mixed, model):
    seq = row["id"]
    source, dest = CACHE / "sequences" / seq, WORK / seq
    output = dest / "prepared.json"
    files = ["preview.mp4", "rgb-calibration.json", "gaze.csv", "odometry.csv"]
    if not all((source / f).is_file() for f in files):
        return False
    fingerprint = {
        f: [(source / f).stat().st_size, (source / f).stat().st_mtime_ns] for f in files
    }
    checkpoint = UPSTREAM / "models/models/v1_default.ckpt"
    fingerprint["checkpoint_sha256"] = hashlib.sha256(
        checkpoint.read_bytes()
    ).hexdigest()
    if output.is_file() and json.loads(output.read_text())["inputs"] == fingerprint:
        return True
    dest.mkdir(parents=True, exist_ok=True)
    sample = windows(row, mixed)
    predictions = neural_predict(model, sample)
    votes = dict(zip(sample["t"].tolist(), predictions.tolist()))
    start, end = math.ceil(sample["start"]), math.floor(sample["end"])
    patches = vote_patches(start, end, votes)
    offset = mixed[seq]["calib"] if row["group"] == "alternating" else row["calib_time"]
    origin = float(row["calibration_time"]) / 1e6 - float(offset)
    sheets = {}
    with av.open(str(source / "preview.mp4")) as container:
        stream = container.streams.video[0]
        stream.thread_type = "FRAME"
        stream.thread_count = 3
        projection = GazeProjection(source, origin, stream.width, stream.height)
        for p in patches:
            sheets[p["start"]] = make_sheet(container, stream, projection, p, dest)
    write_json(
        output,
        {
            "inputs": fingerprint,
            "start": start,
            "end": end,
            "votes": votes,
            "sheets": sheets,
        },
    )
    print("Prepared", seq, len(votes), "votes,", len(sheets), "patches", flush=True)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ready-only", action="store_true")
    args = parser.parse_args()
    mixed = {r["id"]: r for r in rows("task16_annotations.csv")}
    torch.set_num_threads(2)
    model = official("v1_default")
    for r in panel():
        if not prepare(r, mixed, model) and not args.ready_only:
            raise SystemExit(f"Download the inputs for {r['id']} first.")


if __name__ == "__main__":
    main()
