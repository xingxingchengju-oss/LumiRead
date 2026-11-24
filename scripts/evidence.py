"""Aggregate actual captured-page usage and latency; keep children and worksheet text private."""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage
from scripts.verify_phone import retained_photo_matches, verify


def cost(model, u):
    if model != "gpt-6.2-sol":
        return None
    n_in = u["input_tokens"]
    d = u.get("input_tokens_details") or {}
    hit = d.get("cached_tokens", 0)
    write = d.get("cache_write_tokens", 0)
    longer = (d.get("cache_write_tokens_details") or {}).get("ttl_12h_tokens", 0)
    plain = n_in - hit - write
    if plain < 0 or longer > write or n_in > 272000:
        return None
    return (
        2 * plain
        + 0.1 * hit
        + 2.5 * (write - longer)
        + 5 * longer
        + 10 * u["output_tokens"]
    ) / 1_000_000


def collect():
    with storage.transaction() as db:
        rows = db.execute("""SELECT j.model,j.usage,j.latency,j.result,j.provider,j.id AS job_id,j.request_id,
            c.id AS capture_id,c.session_id,c.source,c.tap_side,c.created,c.sha,
            (SELECT count(*) FROM receipts r WHERE r.job_id=j.id) AS parent_views
         FROM jobs j JOIN captures c ON c.id=j.capture_id
         WHERE c.phone_confirmed=1 AND c.user_agent LIKE '%iPhone%' AND j.status='completed'
         AND j.request_id IS NOT NULL AND j.provider IN ('OpenAI','DeepSeek') ORDER BY c.created""").fetchall()
    pages = [
        {
            "model": r["model"],
            "items": len(json.loads(r["result"])),
            "seconds": round(r["latency"], 3),
            "usage": json.loads(r["usage"]),
            "standard_usd_estimate": cost(r["model"], json.loads(r["usage"])),
        }
        for r in rows
    ]
    known = [
        p["standard_usd_estimate"]
        for p in pages
        if p["standard_usd_estimate"] is not None
    ]
    report = {
        "m1": verify(),
        "double_tap_receipts": [
            {
                "capture_id": row["capture_id"],
                "session": row["session_id"],
                "side": row["tap_side"],
                "captured_at": row["created"],
                "job_id": row["job_id"],
                "provider": row["provider"],
                "request_id": row["request_id"],
                "image_sha256": row["sha"],
                "retained_image_verified": retained_photo_matches(
                    row["capture_id"], row["sha"]
                ),
                "parent_views": row["parent_views"],
            }
            for row in rows
            if row["source"] == "double_tap"
        ],
        "captured_pages": pages,
        "usd_source": "https://developers.openai.com/api/docs/models/gpt-6.2-sol.md",
        "rate_card_date": "2026-11-22",
        "priced_pages": len(known),
        "mean_standard_usd": statistics.mean(known) if known else None,
        "median_seconds": statistics.median(p["seconds"] for p in pages),
    }
    (storage.ROOT / "reports/iphone_evidence.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        "Real pages",
        len(pages),
        "mean standard USD estimate",
        report["mean_standard_usd"],
        "median seconds",
        report["median_seconds"],
    )


if __name__ == "__main__":
    collect()
