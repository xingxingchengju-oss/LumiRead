"""Gracefully stop only the matching demo supervisor in this workspace."""

import json
import os
import signal
import subprocess
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
runtime = Path(os.environ.get("LUMIREAD_VAR", root / "var")).resolve()
record = runtime / "server.json"
if not record.exists():
    raise SystemExit("No recorded running demo.")
pid = int(json.loads(record.read_text())["pid"])
command = subprocess.run(
    ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, check=True
).stdout
if not any(name in command for name in ("scripts/desktop.py", "scripts/serve.py")) or pid <= 1:
    raise SystemExit("Recorded PID does not match a LumiRead supervisor.")
cwd = subprocess.run(
    ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
    capture_output=True,
    text=True,
    check=True,
)
if "n" + str(root) not in cwd.stdout.splitlines():
    raise SystemExit("Supervisor belongs to a different workspace.")
os.kill(pid, signal.SIGTERM)
for _ in range(100):
    if not record.exists():
        print("LumiRead stopped.")
        break
    time.sleep(0.1)
else:
    raise SystemExit("Shutdown in progress. Check the demo terminal.")
