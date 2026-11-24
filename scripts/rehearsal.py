"""Timestamp a physical rehearsal and validate actual session evidence before signing it off."""

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage
from ml.dkt.inference import model_info
from scripts.verify_phone import retained_photo_matches


def check_latency(db, sid):
    rows = db.execute(
        """SELECT a.id,a.seen,a.raised FROM alerts a JOIN alert_sources s ON s.alert_id=a.id
       WHERE s.transport='lan_https' AND s.iphone=1 AND a.session_id=? ORDER BY a.raised""",
        (sid,),
    ).fetchall()
    latencies = sorted(
        (r["seen"] - r["raised"]) if r["seen"] is not None else math.inf for r in rows
    )
    p = latencies[math.ceil(0.95 * len(rows)) - 1] if rows else math.inf
    report = {
        "session": sid,
        "transport": "lan_https",
        "observations": [
            {"id": r["id"], "raised": r["raised"], "seen": r["seen"]} for r in rows
        ],
        "attempted": len(rows),
        "received": sum(r["seen"] is not None for r in rows),
        "p95_seconds": p if math.isfinite(p) else None,
        "pass": len(rows) >= 30 and p <= 1,
    }
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}))
    if not report["pass"]:
        raise SystemExit(
            "LAN alert acceptance needs 30 real iPhone alerts and P95 ≤1s."
        )
    return report


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["start", "finish", "verify", "latency"])
    p.add_argument("--session")
    p.add_argument("--video", type=Path)
    args = p.parse_args()
    root = storage.runtime() / "rehearsal"
    root.mkdir(parents=True, exist_ok=True)
    current = root / "current.json"
    prior = json.loads(current.read_text()) if current.is_file() else {}
    if args.action in {"verify", "finish"} and not prior:
        raise SystemExit(
            "No timed physical run recorded. Use make rehearsal-start when the iPhone and presenter are ready."
        )
    sid = args.session or prior.get("session")
    with storage.transaction() as db:
        if not db.execute("SELECT 1 FROM sessions WHERE id=?", (sid,)).fetchone():
            raise SystemExit("Choose a paired physical session with SESSION=<id>.")
        if args.action == "latency":
            report = check_latency(db, sid)
            (storage.ROOT / "reports/iphone_lan_latency.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            return
        if args.action == "start":
            record = {"session": sid, "start": time.time(), "model": model_info()}
            if not record["model"]["available"]:
                raise SystemExit("CPU model unavailable.")
            if prior and not prior.get("end"):
                prior["superseded"] = record["start"]
                (root / f"interrupted-{int(prior['start'])}.json").write_text(
                    json.dumps(prior, indent=2)
                )
            current.write_text(json.dumps(record, indent=2))
            print("Timed rehearsal started.", sid)
            return
        if prior.get("session") != sid:
            raise SystemExit("Use the room of the recorded rehearsal.")
        if args.action == "finish":
            if (
                not args.video
                or not args.video.is_file()
                or args.video.stat().st_size < 4096
            ):
                raise SystemExit(
                    "Provide the real rehearsal recording with VIDEO=path."
                )
            if args.video.suffix.lower() not in {".mov", ".mp4", ".webm"}:
                raise SystemExit("Use a QuickTime, MP4 or WebM recording.")
            prior.update(
                end=time.time(),
                video=str(args.video.resolve()),
                video_sha256=file_hash(args.video),
            )
            current.write_text(json.dumps(prior, indent=2))
            (root / f"{sid}-{int(prior['start'])}.json").write_text(
                json.dumps(prior, indent=2)
            )
        if "end" not in prior:
            raise SystemExit("Finish the timed run before verification.")
        start, end = prior["start"], prior["end"]
        if not 0 < end - start <= 900:
            raise SystemExit("The recorded rehearsal must finish within 15 minutes.")
        rows = db.execute(
            """SELECT c.*,j.id AS job,j.request_id,j.provider,j.finished FROM captures c JOIN jobs j ON j.capture_id=c.id
           WHERE c.session_id=? AND c.created>=? AND j.finished<=? AND j.status='completed'
           AND c.phone_confirmed=1 AND c.user_agent LIKE '%iPhone%' AND j.provider IN ('OpenAI','DeepSeek')
           AND EXISTS(SELECT 1 FROM receipts r WHERE r.job_id=j.id AND r.seen<=?)""",
            (sid, start, end, end),
        ).fetchall()
        good = [
            r
            for r in rows
            if r["request_id"]
            and r["source"] in ("double_tap", "camera", "native_camera")
            and retained_photo_matches(r["id"], r["sha"])
        ]
        learner = db.execute(
            "SELECT learner FROM sessions WHERE id=?", (sid,)
        ).fetchone()[0]
        checks = {
            "two_distinct_live_pages": len({r["sha"] for r in good}) >= 2,
            "eye_alert_seen": bool(
                db.execute(
                    "SELECT 1 FROM alerts WHERE session_id=? AND raised>=? AND seen<=?",
                    (sid, start, end),
                ).fetchone()
            ),
            "exercise_answered": bool(
                db.execute(
                    "SELECT 1 FROM practice_attempts WHERE learner=? AND created BETWEEN ? AND ?",
                    (learner, start, end),
                ).fetchone()
            ),
            "recording_integrity": Path(prior["video"]).is_file()
            and file_hash(prior["video"]) == prior["video_sha256"],
            "real_cpu_model": model_info()["available"]
            and model_info()["model_version"] == prior["model"]["model_version"],
        }
        print(json.dumps(checks, indent=2))
        if not all(checks.values()):
            raise SystemExit("Physical rehearsal evidence is incomplete.")
        dest = storage.ROOT / "reports/rehearsal.json"
        source = Path(prior["video"])
        recording = dest.parent / ("LumiRead_Rehearsal" + source.suffix.lower())
        if source.resolve() != recording.resolve():
            shutil.copyfile(source, recording)
        dest.write_text(
            json.dumps(
                {
                    "session": sid,
                    "start": start,
                    "recording": recording.name,
                    "duration_s": end - start,
                    "requests": [r["request_id"] for r in good],
                    "model": model_info(),
                    "video_sha256": prior["video_sha256"],
                    "checks": checks,
                },
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
