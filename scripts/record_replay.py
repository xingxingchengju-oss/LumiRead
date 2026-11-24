"""Record real online regrading of a retained worksheet using a private temporary room."""

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage
from scripts.serve import start_child
from scripts.verify_phone import verify

root = storage.ROOT
src = (
    Path(sys.argv[1]).resolve()
    if len(sys.argv) > 1
    else storage.runtime() / "photos" / (verify()["captures"][0] + ".jpg")
)
if not src.is_file():
    raise SystemExit(
        "Supply PHOTO=path to a retained worksheet with an incorrect answer."
    )
with (
    tempfile.TemporaryDirectory(prefix="lumiread-recording-") as folder,
    ExitStack() as stack,
):
    listen = stack.enter_context(socket.create_server(("127.0.0.1", 0)))
    origin = "http://127.0.0.1:" + str(listen.getsockname()[1])
    env = {**os.environ, "LUMIREAD_VAR": folder, "LUMIREAD_PHONE_ORIGIN": origin}
    start_child(
        stack,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--fd",
            str(listen.fileno()),
            "--no-access-log",
        ],
        env=env,
        pass_fds=(listen.fileno(),),
    )
    for _ in range(100):
        try:
            with urlopen(origin + "/api/v1/health/ready", timeout=1) as res:
                if res.status == 200:
                    break
        except OSError:
            time.sleep(0.1)
    start_child(stack, [sys.executable, "-m", "apps.api.worker"], env=env)
    subprocess.run(
        [
            str(root / "scripts/web.sh"),
            "exec",
            "node",
            "scripts/record-replay.mjs",
            origin,
            str(src),
            str(root / "reports"),
        ],
        check=True,
    )
