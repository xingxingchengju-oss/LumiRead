"""Audit the current desktop release evidence without making another paid request."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read(path):
    return json.loads((ROOT / path).read_text())


def check(condition, message):
    if not condition:
        raise SystemExit(message)


def clean_smoke():
    import os
    import tempfile

    from fastapi.testclient import TestClient

    from apps.api import learning
    from apps.api.main import app
    from ml.dkt.inference import model_info

    with tempfile.TemporaryDirectory() as folder:
        os.environ["LUMIREAD_VAR"] = folder
        with TestClient(app) as client:
            for path in (
                "/",
                "/eye-care",
                "/showcase",
                "/app",
                "/federated",
                "/api/v1/products",
            ):
                check(
                    client.get(path).status_code == 200, "Clean entry failed: " + path
                )
            reading = client.get("/api/v1/eye-care/research").json()
            check(
                len(reading["clips"])
                == reading["metrics"]["splits"]["test"]["recordings"]
                == 30,
                "The eye-care demo requires the frozen held-out recordings",
            )
            dim = client.get("/api/v1/eye-care/excerpts/dim").json()["events"]
            check(
                len(dim) == 1
                and dim[0]["started_at"].endswith("09:45:27")
                and dim[0]["ended_at"].endswith("09:45:37"),
                "Dim-light replay does not match the 30-second rule",
            )
            fed = client.get("/api/v1/federated").json()
            check(len(fed["runs"]) == 3, "The federated report is incomplete")
            hashes = set()
            for key, segment in zip("ABC", ["stable", "near", "dim"], strict=True):
                sid = client.post(
                    "/api/v1/demo/login", json={"account_id": key}
                ).json()["session_id"]
                p = client.get("/api/v1/demo/profile").json()
                hashes.add(p["learner_hash"])
                history = [(r["skill"], r["correct"]) for r in p["history"]]
                m = client.get(f"/api/v1/learners/{p['learner_id']}/mastery").json()
                check(
                    m == learning.mastery(history)
                    and m["model_version"] == model_info()["model_version"],
                    "History / CPU model mismatch",
                )
                raw = client.get(f"/api/v1/sessions/{sid}/clouclip").json()
                check(
                    raw["segment"]["id"] == segment and raw["status"] == "ready",
                    "Clouclip mapping differs",
                )
            check(len(hashes) == 3, "Expected three distinct real learners")
    print(
        "Clean runtime served the eye-care dashboard, measured alerts, model reports and three independently seeded learning profiles."
    )


def check_receipts():
    from ml.dkt.inference import model_info

    fed = read("artifacts/federated/report.json")
    r = read("reports/desktop_rehearsal.json")
    source = read("data/clouclip/segments.json")["segments"]
    check(
        len(r["runs"]) >= 2 and len(r.get("video_sha256", "")) == 64,
        "Missing two recorded desktop runs",
    )
    video = ROOT / "var/rehearsal/LumiRead_Desktop_Rehearsal.webm"
    if video.is_file():
        with video.open("rb") as stream:
            check(
                hashlib.file_digest(stream, "sha256").hexdigest() == r["video_sha256"],
                "The local rehearsal recording differs from its receipt",
            )
    requests = set()
    for i, run in enumerate(r["runs"]):
        check(
            0 < run["seconds"] <= 900
            and run["reset_restored"]
            and run["profile_updated"],
            "Incomplete timed rehearsal",
        )
        check(
            run["cpu_model"] == model_info()["model_version"]
            and run["federated_selected"] == fed["selected"],
            "Rehearsal references a different frozen model",
        )
        check(
            run["revision_count"] == 1
            and run["practice_added"] == 1
            and run["valid_upload_attempts"] == 4
            and set(run["other_accounts_isolated"]) == {"A", "C"},
            "Learning sequence checks missing",
        )
        for edition, answer in [("original", "8"), ("revised", "5")]:
            f = ROOT / "data/demo" / f"worksheet-{edition}.png"
            work = run[edition]
            check(
                work["sha"] == hashlib.sha256(f.read_bytes()).hexdigest(),
                "Worksheet hash mismatch",
            )
            check(
                work["provider"] in {"OpenAI", "DeepSeek"}
                and work["request"]
                and work["request"] not in requests
                and bool(work["usage"]),
                "Missing unique provider receipt",
            )
            requests.add(work["request"])
            check(
                work["answers"] == ["15", answer]
                and work["verdicts"]
                == ["correct", "incorrect" if edition == "original" else "correct"],
                "Changed answer did not change grade",
            )
        for k in "ABC" if i == 0 else "B":
            part = run["care"][k]
            key = {"A": "stable", "B": "near", "C": "dim"}[k]
            check(
                part["segment"] == key
                and part["samples"] == len(source[key]["records"]),
                "Incomplete sensor replay",
            )
            check(
                (k == "A" and not part["events"])
                or (
                    k != "A"
                    and len(part["events"]) == 1
                    and part["events"][0]["ended_at"]
                ),
                "Unexpected alert lifetime",
            )
    vision = read("reports/vision_evaluation.json")
    receipts = read("reports/desktop_vision_receipts.json")["pages"]
    check(
        len(receipts) == vision["pages"] == len({p["image_sha256"] for p in receipts}),
        "Evaluation pages do not match",
    )
    check(
        len({p["request_id"] for p in receipts}) == len(receipts)
        and all(
            p["provider"] in ("OpenAI", "DeepSeek") and p["used"] for p in receipts
        ),
        "Missing evaluation receipts",
    )
    items = [i for p in receipts for i in p["items"]]
    auto = [i for i in items if i["observed"] != "needs_review"]
    check(
        len(items) == vision["labelled"]
        and len(auto) == vision["automatic"]
        and sum(i["expected"] == i["observed"] for i in auto) == vision["agreed"],
        "Evaluation totals differ from row outcomes",
    )
    check(
        vision["passed"] and vision["agreement"] >= 0.90 and vision["coverage"] >= 0.8,
        "Vision acceptance did not pass",
    )
    print(
        "Verified live grading, isolation, two resettable rehearsals, public sensor timestamps, frozen models and the screenshot cohort."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--clean-smoke", action="store_true")
    if p.parse_args().clean_smoke:
        clean_smoke()
    else:
        check_receipts()
