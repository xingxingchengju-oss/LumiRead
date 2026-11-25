"""Run the local-only API, web UI and vision worker on an ordinary computer."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from threading import Thread

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.api import storage


def serve(port):

    if not (ROOT / "apps/web/dist/index.html").is_file():
        raise SystemExit("Build the interface with make web.")
    storage.initialize()
    with socket.create_server(("127.0.0.1", port)) as listener:
        worker = subprocess.Popen([sys.executable, "-m", "apps.api.worker"], cwd=ROOT)
        server = uvicorn.Server(
            uvicorn.Config(
                "apps.api.main:app", host="127.0.0.1", port=port, access_log=False
            )
        )
        # Uvicorn replays its shutdown signal to the embedding process after
        # draining connections. Let the supervisor finish cleaning up its worker.
        def stop(signum, frame):
            server.should_exit = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        def monitor():
            worker.wait()
            server.should_exit = True

        Thread(target=monitor, daemon=True).start()
        record = storage.runtime() / "server.json"
        data = {
            "pid": os.getpid(),
            "mode": "desktop",
            "parent": f"http://127.0.0.1:{port}/app",
        }
        record.write_text(json.dumps(data))
        print(f"LumiRead eye-care dashboard: http://127.0.0.1:{port}/", flush=True)
        print(f"LumiRead product launch: http://127.0.0.1:{port}/showcase", flush=True)
        try:
            server.run(sockets=[listener])
        finally:
            if worker.poll() is None:
                worker.terminate()
                try:
                    worker.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.wait()
            if (
                record.exists()
                and json.loads(record.read_text()).get("pid") == os.getpid()
            ):
                record.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8742)
    serve(parser.parse_args().port)
