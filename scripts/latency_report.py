"""Compute same-clock intake-to-visible-receipt latency for the separate automated LAN run."""

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage

info = json.loads((storage.runtime() / "qa/bench-room.json").read_text())
with storage.transaction() as db:
    rows = db.execute(
        """SELECT a.id,a.seen-a.raised latency,s.transport,a.input_mode FROM alerts a
           JOIN alert_sources s ON s.alert_id=a.id WHERE a.session_id=?""",
        (info["session"],),
    ).fetchall()
if len(rows) != 30 or {r["id"] for r in rows} != set(info["alerts"]):
    raise SystemExit("Incomplete benchmark")
if any(
    r["latency"] is None
    or r["transport"] != "lan_https"
    or r["input_mode"] != "accelerated"
    for r in rows
):
    raise SystemExit("Missing LAN/receipt evidence")
values = sorted(r["latency"] for r in rows)
p95 = values[math.ceil(0.95 * len(values)) - 1]
r = {
    "n": len(values),
    "min_s": min(values),
    "median_s": (values[14] + values[15]) / 2,
    "p95_s": p95,
    "max_s": max(values),
    "input": "Simulated timer via the Mac LAN HTTPS interface, paired camera client on the same Mac",
    "parent": "Visible DOM acknowledged via the parent route in a separate Chromium context",
    "includes_physical_radio_link": False,
    "stage": "server insertion through parent receipt",
    "pass": p95 <= 1,
}
(storage.ROOT / "reports/lan_browser_latency.json").write_text(
    json.dumps(r, indent=2) + "\n"
)
print(r)
if not r["pass"]:
    raise SystemExit(1)
