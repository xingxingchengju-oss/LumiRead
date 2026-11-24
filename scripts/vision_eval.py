"""Print a reproducible 24-page collection pack, then score reference-labelled uploaded worksheets."""

import argparse
import csv
import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.api import storage
from apps.api.vision import SKILLS
from scripts.verify_phone import retained_photo_matches

DATA = storage.ROOT / "data/vision"
LABELS = storage.runtime() / "eval" / "labels.csv"


def problem(page, index):
    skill = SKILLS[(page * 5 + index) % 6]
    a, b = 2 + (page + index) % 8, 3 + (page * 3 + index) % 7
    if skill == "mixed_arithmetic":
        q, answer = f"{a} + {b} × 3", str(a + b * 3)
    elif skill == "fractions":
        from fractions import Fraction

        q, answer = f"1/{a} + 1/{a * 2}", str(Fraction(3, a * 2))
    elif skill == "decimals":
        q, answer = f"{a / 10:.1f} × {b / 10:.1f}", f"{a * b / 100:.2f}"
    elif skill == "equations":
        q, answer = f"{a}x + 3 = {a * b + 3}. Find x.", str(b)
    elif skill == "area":
        q, answer = (
            f"A rectangle is {a} cm long and {b} cm wide. Find its area in square centimetres.",
            str(a * b),
        )
    else:
        q, answer = (
            f"There are {a} bags of {b} apples. Two apples are eaten. How many remain?",
            str(a * b - 2),
        )
    return skill, q, answer


def pack():
    blocks = []
    for page in range(24):
        rows = "".join(
            f"<li>{html.escape(problem(page, i)[1])}<div>Answer</div></li>"
            for i in range(5)
        )
        blocks.append(
            f"<section><header>LumiRead &nbsp; / &nbsp; Mathematics</header><h1>Worksheet {page + 1:02}</h1><ol>{rows}</ol></section>"
        )
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "worksheets.html").write_text(
        """<!doctype html><html lang="en"><meta charset="utf-8"><title>LumiRead · 24 worksheets</title>
<style>@page{size:A4;margin:18mm}body{font:18px Georgia,serif;background:#eee;color:#15221c;margin:0}
section{background:white;padding:14mm;max-width:170mm;margin:10mm auto;break-after:page}section:last-child{break-after:auto}h1{font-size:32px}
header{font:14px system-ui;color:#384e40}li{padding:14px 0}li div{font-size:14px;margin:12px 0 0;border-bottom:1px solid #555;height:34px;color:#46554c}
@media print{body{background:white}section{padding:0;margin:0;max-width:none}}</style>"""
        + "".join(blocks)
        + "</html>"
    )
    print(DATA / "worksheets.html")


def labels():
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with storage.transaction() as db:
        rows = db.execute("""SELECT c.id,c.created,c.sha FROM captures c
                           WHERE source='upload' ORDER BY created""").fetchall()
    print("Uploaded worksheets (UTC timestamps, no grades):")
    from datetime import UTC, datetime

    for r in rows:
        print(
            datetime.fromtimestamp(r["created"], UTC).isoformat(),
            r["id"],
            r["sha"][:12],
        )
    if not LABELS.exists():
        with LABELS.open("x", newline="") as f:
            w = csv.writer(f)
            w.writerow(
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
            for p in range(24):
                for i in range(5):
                    skill, q, ref = problem(p, i)
                    w.writerow([p + 1, i + 1, skill, ref, "", q, "", "", "", i + 1])
    print("Independent labels:", LABELS)


def evaluate(path, dest=None):
    rows = list(csv.DictReader(path.open())) if path.is_file() else []
    if not rows:
        raise SystemExit(
            "Run make vision-labels and label retained uploaded worksheets, or run make evaluate-desktop-vision for the keyed screenshot evaluation."
        )
    refs = set()
    matched = set()
    photos = {}
    skills = Counter()
    counts = Counter()
    seen_pages = {}
    with storage.transaction() as db:
        for row in rows:
            cid = row["capture_id"].strip()
            verdict = row["human_verdict"].strip()
            if (
                not cid
                or not row["annotator"].strip()
                or not row["photo_question"].strip()
                or verdict not in ("correct", "incorrect", "needs_review")
            ):
                raise SystemExit(
                    "Each reference row needs an image, transcription, verdict and reference source."
                )
            if row["skill"] not in SKILLS or not row["handwritten_answer"].strip():
                raise SystemExit(
                    "Complete the skill and the observed answer (use [blank] for a blank)."
                )
            pos = int(row["ordinal"])
            if (
                pos < 1
                or (cid, pos) in refs
                or seen_pages.setdefault(row["page"], cid) != cid
            ):
                raise SystemExit("Invalid repeated/ambiguous reference")
            refs.add((cid, pos))
            if cid not in photos:
                r = db.execute(
                    """SELECT c.*,j.result,j.provider,j.request_id FROM captures c JOIN jobs j ON j.capture_id=c.id
                             WHERE c.id=? AND j.status='completed'""",
                    (cid,),
                ).fetchone()
                if (
                    not r
                    or r["source"] != "upload"
                    or r["provider"] not in ("OpenAI", "DeepSeek")
                    or not r["request_id"]
                    or not retained_photo_matches(cid, r["sha"])
                ):
                    raise SystemExit(
                        "Missing upload or real-provider evidence for " + cid
                    )
                photos[cid] = (r["sha"], json.loads(r["result"]))
            skills[row["skill"]] += 1
            counts["labelled"] += 1
            index = int(row["provider_ordinal"] or 0)
            if not index:
                counts["unread"] += 1
                continue
            if (cid, index) in matched or index < 1 or index > len(photos[cid][1]):
                raise SystemExit(
                    "Enter the matching provider ordinal; use 0 if missed."
                )
            matched.add((cid, index))
            prediction = photos[cid][1][index - 1]["verdict"]
            if prediction != "needs_review":
                counts["automatic"] += 1
                counts["agree"] += prediction == verdict
    extra = sum(len(items) for _, items in photos.values()) - len(matched)
    agreement = counts["agree"] / max(1, counts["automatic"] + extra)
    coverage = counts["automatic"] / max(1, counts["labelled"])
    report = {
        "input": "ordinary worksheet upload",
        "reference_sources": sorted({r["annotator"] for r in rows}),
        "pages": len({sha for sha, _ in photos.values()}),
        "labelled": counts["labelled"],
        "skills": dict(skills),
        "automatic": counts["automatic"],
        "agreed": counts["agree"],
        "unmatched_predictions": extra,
        "agreement": agreement,
        "coverage": coverage,
        "labels_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    report["passed"] = (
        report["pages"] >= 24
        and 100 <= counts["labelled"] <= 200
        and set(skills) == set(SKILLS)
        and agreement >= 0.9
        and coverage >= 0.8
    )
    dest = dest or storage.ROOT / "reports/uploaded_photo_evaluation.json"
    dest.write_text(json.dumps(report, indent=2) + "\n")
    print(dest.read_text())
    if not report["passed"]:
        raise SystemExit("Evaluation misses an acceptance threshold.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pack", "labels", "evaluate"])
    parser.add_argument("--labels", type=Path, default=LABELS)
    args = parser.parse_args()
    if args.action == "pack":
        pack()
    elif args.action == "labels":
        labels()
    else:
        evaluate(args.labels)
