"""Versioned worksheet results and learner history. Original provider responses stay immutable."""

import hashlib
import json
import time
from collections import Counter
from fractions import Fraction

from fastapi import HTTPException

from . import storage
from .vision import SKILLS

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions(
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs, ordinal INTEGER NOT NULL,
 revision INTEGER NOT NULL DEFAULT 0, result TEXT NOT NULL, UNIQUE(job_id,ordinal));
CREATE TABLE IF NOT EXISTS question_revisions(
 question_id TEXT NOT NULL REFERENCES questions, revision INTEGER NOT NULL, result TEXT NOT NULL,
 receipt TEXT, created REAL NOT NULL, PRIMARY KEY(question_id,revision));
CREATE TABLE IF NOT EXISTS mistakes(learner TEXT NOT NULL REFERENCES learners,
 question_id TEXT NOT NULL REFERENCES questions, created REAL NOT NULL, PRIMARY KEY(learner,question_id));
CREATE TABLE IF NOT EXISTS recommendations(id TEXT PRIMARY KEY, learner TEXT NOT NULL REFERENCES learners,
 generation TEXT NOT NULL, slot INTEGER NOT NULL, skill TEXT NOT NULL, question TEXT NOT NULL,
 answer TEXT NOT NULL, explanation TEXT NOT NULL, UNIQUE(learner,generation,slot));
CREATE TABLE IF NOT EXISTS practice_attempts(recommendation_id TEXT PRIMARY KEY REFERENCES recommendations,
 learner TEXT NOT NULL REFERENCES learners, idem TEXT NOT NULL, answer TEXT NOT NULL, correct INTEGER NOT NULL,
 created REAL NOT NULL, UNIQUE(learner,idem));
CREATE INDEX IF NOT EXISTS attempts_history ON attempts(learner,created);
"""


def save_questions(db, jid, items):
    for n, row in enumerate(items, 1):
        db.execute(
            "INSERT OR IGNORE INTO questions(id,job_id,ordinal,result) VALUES(?,?,?,?)",
            (f"{jid}.{n}", jid, n, json.dumps(row, ensure_ascii=False)),
        )


def result(row):
    return {**json.loads(row["result"]), "id": row["id"], "revision": row["revision"]}


def current_results(db, jid):
    return [
        result(r)
        for r in db.execute(
            "SELECT * FROM questions WHERE job_id=? ORDER BY ordinal", (jid,)
        )
    ]


def changed(db, learner):
    for row in db.execute("SELECT id FROM sessions WHERE learner=?", (learner,)):
        for kind in ("mastery.updated", "recommendations.ready"):
            storage.event(db, row["id"], kind, {"learner_id": learner})


def history(db, learner):
    baseline = [
        (row["skill"], bool(row["correct"]))
        for row in db.execute(
            "SELECT skill,correct FROM demo_history WHERE learner=? ORDER BY source_order",
            (learner,),
        )
    ]
    return baseline + [
        (row["skill"], bool(row["correct"]))
        for row in db.execute(
            """
        SELECT skill,correct,created,job_id AS source,ordinal FROM attempts WHERE learner=?
        UNION ALL SELECT r.skill,a.correct,a.created,r.id,0 FROM practice_attempts a
        JOIN recommendations r ON r.id=a.recommendation_id WHERE a.learner=?
        ORDER BY created,source,ordinal""",
            (learner, learner),
        )
    ]


def mastery(records):
    try:
        from ml.dkt.inference import model_info, predict

        info = model_info()
        if not info["available"]:
            raise ValueError("DKT unavailable")
        probs = predict(records)
        version = info.get("model_version") or info.get("version")
        if not version or any(s not in probs or not 0 <= probs[s] <= 1 for s in SKILLS):
            raise ValueError("Invalid model output")
    except (ImportError, FileNotFoundError, ValueError, OSError):
        probs, version = {}, None
    counts = Counter(skill for skill, correct in records)
    return {
        "available": bool(probs),
        "device": "cpu",
        "model_version": version,
        "skills": [
            {"skill": s, "probability": probs.get(s), "evidence_count": counts[s]}
            for s in SKILLS
        ],
    }


def practice_item(skill, seed):
    a, b, c = 2 + seed % 9, 2 + seed // 11 % 8, 2 + seed // 101 % 6
    if skill == "fractions":
        return (
            f"计算并约分：1/{a} + 1/{2 * a}",
            str(Fraction(3, 2 * a)),
            f"通分到 {2 * a} 后，把分子 2 和 1 相加，再约分。",
        )
    if skill == "decimals":
        return (
            f"计算：{a / 10:.1f} × {b / 10:.1f}",
            f"{a * b / 100:.2f}",
            f"整数相乘得到 {a * b}，乘积共有两位小数。",
        )
    if skill == "equations":
        return (
            f"若 {a}x + {c} = {a * b + c}，x 等于多少？",
            str(b),
            f"两边减 {c}，再除以 {a}。",
        )
    if skill == "area":
        return (
            f"三角形底 {2 * a} 厘米，高 {b} 厘米。面积是多少平方厘米？",
            str(a * b),
            f"底乘高除以 2，计算 {2 * a} × {b} ÷ 2。",
        )
    if skill == "word_modeling":
        return (
            f"图书角有 {a} 层书架，每层 {b} 本，又借出 {c} 本。请列式计算剩下的本数。",
            str(a * b - c),
            f"先用 {a} × {b} 求总数，再减去借出的 {c} 本。",
        )
    return f"计算：{a} + {b} × {c}", str(a + b * c), f"先乘 {b} × {c}，再加 {a}。"


def recommend(db, learner):
    records = history(db, learner)
    profile = mastery(records)
    if not profile["available"]:
        return []
    generation = hashlib.sha256(
        json.dumps([profile["model_version"], records]).encode()
    ).hexdigest()
    ranked = sorted(profile["skills"], key=lambda r: (r["probability"], r["skill"]))
    for i, row in enumerate(ranked[:2]):
        key = hashlib.sha256(f"{learner}/{generation}/{i}".encode()).hexdigest()[:32]
        q, answer, explanation = practice_item(row["skill"], int(key, 16))
        db.execute(
            "INSERT OR IGNORE INTO recommendations VALUES(?,?,?,?,?,?,?,?)",
            (key, learner, generation, i, row["skill"], q, answer, explanation),
        )
    return [
        dict(row)
        for row in db.execute(
            """SELECT id,skill,question FROM recommendations
            WHERE learner=? AND generation=? ORDER BY slot""",
            (learner, generation),
        )
    ]


def practice_answer(db, learner, rid, answer, idem):
    from .worker import numeric

    row = db.execute(
        "SELECT * FROM recommendations WHERE id=? AND learner=?", (rid, learner)
    ).fetchone()
    if not row:
        raise HTTPException(404, "未找到这道巩固题")
    previous = db.execute(
        "SELECT * FROM practice_attempts WHERE learner=? AND (idem=? OR recommendation_id=?)",
        (learner, idem, rid),
    ).fetchone()
    if previous:
        if (previous["recommendation_id"], previous["idem"], previous["answer"]) != (
            rid,
            idem,
            answer,
        ):
            raise HTTPException(409, "该作答已提交，请刷新练习。")
        correct = bool(previous["correct"])
    else:
        val = numeric(answer)
        if val is None:
            raise HTTPException(422, "请输入数值、分数或四则算式。")
        correct = val == numeric(row["answer"])
        db.execute(
            "INSERT INTO practice_attempts VALUES(?,?,?,?,?,?)",
            (rid, learner, idem, answer, int(correct), time.time()),
        )
        changed(db, learner)
    return {
        "question": row["question"],
        "correct": correct,
        "reference_answer": row["answer"],
        "explanation": row["explanation"],
    }


QUESTION = """SELECT q.*,s.learner,c.session_id,c.id AS capture_id,c.created AS captured
 FROM questions q JOIN jobs j ON q.job_id=j.id JOIN captures c ON c.id=j.capture_id
 JOIN sessions s ON s.id=c.session_id WHERE q.id=? AND s.learner=?"""


def reviewed(db, original, item, receipt):
    rev = original["revision"] + 1
    raw = json.dumps(item, ensure_ascii=False)
    changed_rows = db.execute(
        "UPDATE questions SET revision=?, result=? WHERE id=? AND revision=?",
        (rev, raw, original["id"], rev - 1),
    ).rowcount
    if not changed_rows:
        raise HTTPException(409, "题目已更新，请刷新后重新核对。")
    db.execute(
        "INSERT INTO question_revisions VALUES(?,?,?,?,?)",
        (original["id"], rev, raw, json.dumps(receipt), time.time()),
    )
    if item["verdict"] == "needs_review":
        db.execute(
            "DELETE FROM attempts WHERE job_id=? AND ordinal=?",
            (original["job_id"], original["ordinal"]),
        )
    else:
        db.execute(
            """INSERT INTO attempts VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_id,ordinal)
                   DO UPDATE SET skill=excluded.skill,correct=excluded.correct""",
            (
                storage.uid(),
                original["learner"],
                original["job_id"],
                original["ordinal"],
                item["skill"],
                int(item["verdict"] == "correct"),
                original["captured"],
            ),
        )
    storage.event(
        db,
        original["session_id"],
        "question.reviewed",
        {"question_id": original["id"], "revision": rev},
    )
    changed(db, original["learner"])
    return {**item, "id": original["id"], "revision": rev}
