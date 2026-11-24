"""Launch a fresh isolated desktop runtime and film the real browser rehearsal."""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    base = ROOT / "var/rehearsal"
    base.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="desktop-", dir=base))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    env = {**os.environ, "LUMIREAD_VAR": str(folder / "runtime")}
    cached = ROOT / ".cache/field-browsers"
    if not env.get("PLAYWRIGHT_BROWSERS_PATH") and list(cached.glob("ffmpeg-*")):
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(cached)
    with (folder / "service.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "scripts/desktop.py", "--port", str(port)],
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(120):
                if server.poll() is not None:
                    raise SystemExit("Rehearsal service exited. See " + str(log.name))
                try:
                    health = httpx.get(url + "/api/v1/health/ready", timeout=2).json()
                    if not health["vision_configured"]:
                        raise SystemExit("Configure the backend vision API key.")
                    if health["model"]["available"]:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            else:
                raise SystemExit("Rehearsal service startup timed out.")
            subprocess.run(
                [
                    "./scripts/web.sh",
                    "exec",
                    "node",
                    "scripts/desktop-rehearsal.mjs",
                    url,
                    str(folder),
                ],
                cwd=ROOT,
                env=env,
                check=True,
            )
            report = json.loads((folder / "rehearsal.json").read_text())
            (ROOT / "reports/desktop_rehearsal.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            private_video = base / "LumiRead_Desktop_Rehearsal.webm"
            shutil.copyfile(
                folder / private_video.name, private_video.with_suffix(".tmp")
            )
            private_video.with_suffix(".tmp").replace(private_video)
            print(
                "Local rehearsal recording:", folder / "LumiRead_Desktop_Rehearsal.webm"
            )
        finally:
            server.terminate()
            try:
                server.wait(timeout=12)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        if server.returncode != 0 or (folder / "runtime/server.json").exists():
            raise SystemExit("The rehearsal supervisor did not stop cleanly.")


if __name__ == "__main__":
    main()
