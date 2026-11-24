"""Check real capture → provider → parent evidence, without exposing worksheet text."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage


def retained_photo_matches(capture_id, expected_hash):
    photo_path = storage.runtime() / "photos" / (capture_id + ".jpg")
    try:
        with photo_path.open("rb") as photo:
            return hashlib.file_digest(photo, "sha256").hexdigest() == expected_hash
    except FileNotFoundError:
        return False


def verify(sid=None):
    with storage.transaction() as db:
        rows = db.execute(
            """SELECT j.*,c.session_id,c.sha,c.source,c.user_agent,c.phone_confirmed,c.camera_model,
            (SELECT COUNT(*) FROM receipts r WHERE r.job_id=j.id) views
            FROM jobs j JOIN captures c ON j.capture_id=c.id
            WHERE j.status='completed' AND (? IS NULL OR c.session_id=?) ORDER BY c.created""",
            (sid, sid),
        ).fetchall()
    candidates = [
        r
        for r in rows
        if r["provider"] in ("OpenAI", "DeepSeek")
        and r["request_id"]
        and r["source"] in ("camera", "native_camera", "double_tap", "gesture")
        and "iPhone" in r["user_agent"]
        and r["phone_confirmed"]
        and r["camera_model"] in ("", None, "iPhone 16 Pro Max")
        and r["views"] >= 1
        and retained_photo_matches(r["capture_id"], r["sha"])
    ]

    def key(s):
        return "".join(s.split()).casefold().rstrip("=？?")

    for i, a in enumerate(candidates):
        items = json.loads(a["result"])
        if not {"correct", "incorrect"}.issubset({j["verdict"] for j in items}):
            continue
        for b in candidates[i + 1 :]:
            if (
                a["session_id"] != b["session_id"]
                or a["sha"] == b["sha"]
                or a["request_id"] == b["request_id"]
                or b["views"] < 2
            ):
                continue
            for old in items:
                for new in json.loads(b["result"]):
                    if (
                        key(old["question"]) == key(new["question"])
                        and old["student_answer"] != new["student_answer"]
                        and {old["verdict"], new["verdict"]} == {"incorrect", "correct"}
                    ):
                        return {
                            "session_id": a["session_id"],
                            "captures": [a["capture_id"], b["capture_id"]],
                            "jobs": [a["id"], b["id"]],
                            "providers": [a["provider"], b["provider"]],
                            "requests": [a["request_id"], b["request_id"]],
                            "images_sha256": [a["sha"], b["sha"]],
                            "parent_page_views": [a["views"], b["views"]],
                            "device_evidence": "operator confirmation and iPhone user agent; EXIF checked when available",
                        }
    raise SystemExit(
        f"M1 pending. {len(candidates)} eligible real iPhone capture(s) acknowledged by the parent UI. "
        "Use a page with one correct and one incorrect answer. Change an answer, photograph again, then reload the parent page."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    args = parser.parse_args()
    print(json.dumps(verify(args.session), indent=2))
