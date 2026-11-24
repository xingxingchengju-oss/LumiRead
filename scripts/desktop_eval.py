"""Render keyed worksheets, then score real vision calls through ordinary parent uploads."""

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evidence import cost
from scripts.vision_eval import problem

WORK = ROOT / "var/worksheet-evaluation"
EXAMPLES = ROOT / "data/demo"


def sheets():
    result = []
    for n in range(24):
        rows = []
        for i in range(5):
            skill, question, ref = problem(n, i)
            wrong = (n + i) % 3 == 0
            answer = "999" if wrong else ref
            rows.append(
                {
                    "skill": skill,
                    "question": question,
                    "answer": answer,
                    "reference": ref,
                    "verdict": "incorrect" if wrong else "correct",
                }
            )
        result.append(
            {
                "title": f"Mathematics  |  Practice sheet {n + 1:02}",
                "path": str(WORK / f"page-{n + 1:02}.png"),
                "items": rows,
            }
        )
    for edition, answer in [("original", "8"), ("revised", "5")]:
        result.append(
            {
                "title": "Arithmetic practice",
                "path": str(EXAMPLES / f"worksheet-{edition}.png"),
                "items": [
                    {"question": "8 + 7 = ?", "answer": "15"},
                    {"question": "9 - 4 = ?", "answer": answer},
                ],
            }
        )
    return result


def render(pages):
    WORK.mkdir(parents=True, exist_ok=True)
    manifest = WORK / "answer-key.json"
    manifest.write_text(json.dumps(pages, ensure_ascii=False, indent=2))
    subprocess.run(
        [
            "./scripts/web.sh",
            "exec",
            "node",
            "scripts/render-worksheets.mjs",
            str(manifest),
        ],
        cwd=ROOT,
        check=True,
    )


def evaluate():
    from fastapi.testclient import TestClient

    from apps.api import vision, worker
    from apps.api.main import app
    from scripts.vision_eval import evaluate as score

    if not any(p[3] for p in vision.config()):
        raise SystemExit(
            "Configure a backend vision key before starting an online evaluation."
        )
    os.environ["LUMIREAD_VAR"] = str(WORK / "runtime")
    prior = json.loads((WORK / "answer-key.json").read_text())
    if prior != sheets():
        raise SystemExit("Worksheet references changed. Render the pages again.")
    rows, evidence = [], []
    with TestClient(app) as client:
        login = client.post("/api/v1/demo/login", json={"account_id": "B"})
        login.raise_for_status()
        sid = login.json()["session_id"]
        for n, sheet in enumerate(prior[:24], 1):
            path = Path(sheet["path"])
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            response = client.post(
                f"/api/v1/sessions/{sid}/captures",
                data={"source": "upload", "idem": "benchmark-" + digest},
                files={"photo": (path.name, raw, "image/png")},
            )
            response.raise_for_status()
            cid, jid = response.json()["capture_id"], response.json()["job_id"]
            job = client.get("/api/v1/jobs/" + jid).json()
            if job["status"] == "failed":
                client.post(f"/api/v1/jobs/{jid}/retry").raise_for_status()
            if job["status"] != "completed":
                worker.run_one()
                job = client.get("/api/v1/jobs/" + jid).json()
            if (
                job["status"] != "completed"
                or job["provider"] not in ("OpenAI", "DeepSeek")
                or not job["request_id"]
            ):
                raise SystemExit(f"Online grading failed on page {n}: {job['error']}")
            results = job["result"]
            if len(results) != len(sheet["items"]):
                raise SystemExit(
                    f"Page {n}: align {len(results)} detections manually before scoring."
                )
            for i, (item, pred) in enumerate(
                zip(sheet["items"], results, strict=True), 1
            ):
                rows.append(
                    [
                        n,
                        i,
                        item["skill"],
                        item["reference"],
                        cid,
                        item["question"],
                        item["answer"],
                        item["verdict"],
                        "precomputed arithmetic answer key",
                        i,
                    ]
                )
            evidence.append(
                {
                    "page": n,
                    "capture_id": cid,
                    "job_id": jid,
                    "image_sha256": digest,
                    "request_id": job["request_id"],
                    "provider": job["provider"],
                    "model": job["model"],
                    "used": job["usage"],
                    "seconds": job["latency"],
                    "estimated_usd": cost(job["model"], job["usage"]),
                    "items": [
                        {
                            "expected": a["verdict"],
                            "observed": b["verdict"],
                            "question_read": b["question"],
                            "answer_read": b["student_answer"],
                        }
                        for a, b in zip(sheet["items"], results)
                    ],
                }
            )
            print(
                f"{n}/24 · {job['provider']} · {len(results)} real grades", flush=True
            )
    labels = WORK / "keyed.csv"
    with labels.open("w", newline="") as f:
        out = csv.writer(f)
        out.writerow(
            [
                "page",
                "ordinal",
                "skill",
                "reference",
                "capture_id",
                "photo_question",
                "handwritten_answer",
                "human_verdict",
                "annotator",
                "provider_ordinal",
            ]
        )
        out.writerows(rows)
    (ROOT / "reports/desktop_vision_receipts.json").write_text(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "input": "browser-rendered typeset worksheet screenshots with fixed reference answers",
                "pages": evidence,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    score(labels, ROOT / "reports/vision_evaluation.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--render-only", action="store_true")
    args = p.parse_args()
    if (
        args.render_only
        or not (WORK / "answer-key.json").exists()
        or not all(Path(p["path"]).is_file() for p in sheets())
    ):
        render(sheets())
    if not args.render_only:
        evaluate()
