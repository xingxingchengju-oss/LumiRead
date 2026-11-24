"""Run as a separate process. Expired leases are recoverable after a crash."""

import ast
import json
import operator
import re
import time

from sympy import Rational

from . import learning, storage
from .vision import ProviderFailure, grade_photo

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def numeric(text):
    expr = (
        text.strip()
        .rstrip("=?？ ")
        .translate(str.maketrans({"×": "*", "÷": "/", "−": "-", "（": "(", "）": ")"}))
    )
    if not expr or len(expr) > 100 or not re.fullmatch(r"[\d.+*/()\s-]+", expr):
        return None
    try:
        root = ast.parse(expr, mode="eval")
        if len(list(ast.walk(root))) > 48:
            return None

        def value(node):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                part = ast.get_source_segment(expr, node)
                if not part or len(part) > 16:
                    raise ValueError
                return Rational(part)
            if isinstance(node, ast.BinOp) and type(node.op) in OPS:
                left, right = value(node.left), value(node.right)
                if isinstance(node.op, ast.Div) and right == 0:
                    raise ValueError
                return OPS[type(node.op)](left, right)
            if isinstance(node, ast.UnaryOp) and isinstance(
                node.op, (ast.UAdd, ast.USub)
            ):
                return value(node.operand) * (
                    -1 if isinstance(node.op, ast.USub) else 1
                )
            raise ValueError

        return value(root.body)
    except (SyntaxError, ValueError, ArithmeticError):
        return None


def check_items(grade):
    items = []
    for item in grade.items:
        row = item.model_dump()
        row["verification"] = "visual"
        expected, reference, student = map(
            numeric, (item.question, item.reference_answer, item.student_answer)
        )
        if item.verdict != "needs_review" and all(
            v is not None for v in (expected, reference, student)
        ):
            if expected != reference or (expected == student) != (
                item.verdict == "correct"
            ):
                row.update(
                    verdict="needs_review",
                    review_reason="视觉判分与独立算式验算不一致，请核对原图。",
                )
                row["verification"] = "conflict"
            else:
                row["verification"] = "sympy"
        items.append(row)
    return items


def run_one(grader=grade_photo):
    now, lease = time.time(), storage.uid()
    with storage.transaction(True) as db:
        job = db.execute(
            """SELECT j.id,j.capture_id,c.session_id,c.created,s.learner FROM jobs j
            JOIN captures c ON c.id=j.capture_id JOIN sessions s ON s.id=c.session_id
            WHERE j.status='queued' OR (j.status='running' AND j.lease_until<?)
            ORDER BY c.created LIMIT 1""",
            (now,),
        ).fetchone()
        if not job:
            return False
        db.execute(
            "UPDATE jobs SET status='running',lease=?,lease_until=?,error=NULL WHERE id=?",
            (lease, now + 240, job["id"]),
        )
        storage.event(db, job["session_id"], "grading.running", {"job_id": job["id"]})
    try:
        photo = (
            storage.runtime() / "photos" / (job["capture_id"] + ".jpg")
        ).read_bytes()
        grade, meta = grader(photo)
        rows = check_items(grade)
        fail = None
    except (OSError, ProviderFailure) as exc:
        fail = str(exc) if isinstance(exc, ProviderFailure) else "作业图片不可读取"
    with storage.transaction(True) as db:
        owner = db.execute("SELECT lease FROM jobs WHERE id=?", (job["id"],)).fetchone()
        if not owner or owner["lease"] != lease:
            return True
        if fail:
            db.execute(
                "UPDATE jobs SET status='failed',lease=NULL,error=?,finished=? WHERE id=?",
                (fail, time.time(), job["id"]),
            )
            kind = "grading.failed"
        else:
            db.execute(
                """UPDATE jobs SET status='completed',result=?,provider=?,model=?,request_id=?,
                usage=?,latency=?,finished=?,lease=NULL WHERE id=?""",
                (
                    json.dumps(rows, ensure_ascii=False),
                    meta["provider"],
                    meta["model"],
                    meta["request_id"],
                    json.dumps(meta["usage"]),
                    time.time() - now,
                    time.time(),
                    job["id"],
                ),
            )
            learning.save_questions(db, job["id"], rows)
            for n, item in enumerate(rows, 1):
                if item["verdict"] != "needs_review":
                    db.execute(
                        """INSERT INTO attempts(id,learner,job_id,ordinal,skill,correct,created)
                        VALUES(?,?,?,?,?,?,?)""",
                        (
                            storage.uid(),
                            job["learner"],
                            job["id"],
                            n,
                            item["skill"],
                            int(item["verdict"] == "correct"),
                            job["created"],
                        ),
                    )
            kind = "grading.completed"
        storage.event(db, job["session_id"], kind, {"job_id": job["id"]})
        if not fail:
            learning.changed(db, job["learner"])
    return True


if __name__ == "__main__":
    storage.initialize()
    while True:
        if not run_one():
            time.sleep(0.35)
