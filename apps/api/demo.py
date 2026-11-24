"""Local demonstration identities with independent, resettable learner histories."""

import json
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from . import contracts, storage
from .vision import SKILLS, Skill

REGISTRY = {
    "A": ("初次观察", "从一段较短的真实学习记录开始。", "stable"),
    "B": ("专项练习", "观察同一知识点上的多次练习。", "near"),
    "C": ("综合观察", "查看较长学习历史中的多个知识点。", "dim"),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS demo_accounts (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE REFERENCES sessions,
 learner TEXT NOT NULL UNIQUE REFERENCES learners, baseline TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demo_history (
 learner TEXT NOT NULL REFERENCES learners, source_order INTEGER NOT NULL,
 skill TEXT NOT NULL, correct INTEGER NOT NULL, original_time TEXT,
 PRIMARY KEY(learner,source_order)
);
"""
SEEDS = storage.ROOT / "data/dkt/demo_accounts.json"


class Login(BaseModel):
    account_id: Literal["A", "B", "C"]


class Reset(BaseModel):
    session_id: str


class Account(BaseModel):
    id: Literal["A", "B", "C"]
    name: str
    description: str
    segment: Literal["stable", "near", "dim"]


class Accounts(BaseModel):
    accounts: list[Account]


class HistoricalAnswer(BaseModel):
    source_order: int
    skill: Skill
    correct: bool
    original_time: str | None


class Profile(Account):
    account_id: Literal["A", "B", "C"]
    session_id: str
    learner_id: str
    learner_hash: str
    split: Literal["validation", "test"]
    source: str
    selection: str
    time_basis: str
    history: list[HistoricalAnswer]


def info(account_id):
    name, description, segment = REGISTRY[account_id]
    return {
        "id": account_id,
        "name": name,
        "description": description,
        "segment": segment,
    }


def seed(account_id):
    if not SEEDS.is_file():
        raise HTTPException(
            503, "请在演示电脑运行 make demo-accounts，准备真实学习历史。"
        )
    data = json.loads(SEEDS.read_text())
    row = next(r for r in data["accounts"] if r["id"] == account_id)
    events = row["events"]
    orders = [e["problem_log_id"] for e in events]
    if (
        row["split"] not in ("validation", "test")
        or not events
        or len(orders) != len(set(orders))
        or orders != sorted(orders)
        or any(e["skill"] not in SKILLS or e["correct"] not in (0, 1) for e in events)
    ):
        raise HTTPException(503, "学习历史与已冻结的数据划分不一致。")
    return {
        "source": "ASSISTments 2009–2010 · Skill Builder 修正版",
        "selection": {
            "A": "按预注册规则选取 3–5 次作答的短历史。",
            "B": "按预注册规则选取 12–45 次作答，且同一知识点至少 12 次、占总数至少 70%。",
            "C": "按预注册规则选取至少 40 次作答且覆盖至少 4 个知识点的序列。",
        }[account_id],
        "split": row["split"],
        "learner_hash": row["learner_hash"],
        "time_basis": "按原始 order_id 排序。源文件未提供作答日期和时刻。",
    }, events


def create(db, account_id):
    from . import clouclip

    meta, events = seed(account_id)
    learner, sid = storage.uid(), storage.uid()
    db.execute("INSERT INTO learners VALUES(?)", (learner,))
    db.execute(
        "INSERT INTO sessions(id,learner,created) VALUES(?,?,?)",
        (sid, learner, time.time()),
    )
    db.executemany(
        "INSERT INTO demo_history VALUES(?,?,?,?,?)",
        [
            (
                learner,
                e["problem_log_id"],
                e["skill"],
                int(e["correct"]),
                e["observed_at"],
            )
            for e in events
        ],
    )
    db.execute(
        "INSERT INTO demo_accounts VALUES(?,?,?,?)",
        (account_id, sid, learner, json.dumps(meta, ensure_ascii=False)),
    )
    clouclip.bind(db, sid, info(account_id)["segment"])
    return sid


def find(db, sid):
    return db.execute(
        "SELECT * FROM demo_accounts WHERE session_id=?", (sid,)
    ).fetchone()


def require_account(db, request, member):
    access = member(db, request, roles=("parent",))
    account = find(db, access["session_id"])
    if not account:
        raise HTTPException(403, "请先选择演示账号。")
    return account


def remove(db, account):
    """Remove this generation atomically. In-flight workers check their lease at commit."""
    sid, learner = account["session_id"], account["learner"]
    captures = db.execute(
        "SELECT id FROM captures WHERE session_id=?", (sid,)
    ).fetchall()
    jobs = "SELECT j.id FROM jobs j JOIN captures c ON c.id=j.capture_id WHERE c.session_id=?"
    db.execute(
        "DELETE FROM question_revisions WHERE question_id IN (SELECT id FROM questions WHERE job_id IN ("
        + jobs
        + "))",
        (sid,),
    )
    db.execute("DELETE FROM receipts WHERE job_id IN (" + jobs + ")", (sid,))
    for table in (
        "mistakes",
        "attempts",
        "practice_attempts",
        "recommendations",
        "demo_history",
    ):
        db.execute(f"DELETE FROM {table} WHERE learner=?", (learner,))
    db.execute("DELETE FROM questions WHERE job_id IN (" + jobs + ")", (sid,))
    db.execute(
        "DELETE FROM jobs WHERE capture_id IN (SELECT id FROM captures WHERE session_id=?)",
        (sid,),
    )
    for table in ("captures", "invites", "tickets", "events", "demo_accounts"):
        db.execute(f"DELETE FROM {table} WHERE session_id=?", (sid,))
    db.execute("DELETE FROM sessions WHERE id=?", (sid,))
    db.execute("DELETE FROM learners WHERE id=?", (learner,))
    return [row["id"] for row in captures]


def make_router(member, ticket, cookie):
    router = APIRouter()

    @router.get("/demo/accounts", response_model=Accounts)
    def accounts():
        return {"accounts": [info(i) for i in REGISTRY]}

    @router.post("/demo/login", response_model=contracts.Session)
    def login(body: Login, request: Request, response: Response):
        if request.client.host not in (
            "127.0.0.1",
            "::1",
            "testclient",
        ) or request.url.hostname not in (
            "localhost",
            "127.0.0.1",
            "::1",
            "testserver",
        ):
            raise HTTPException(403, "请在演示电脑的本机入口登录。")
        with storage.transaction(True) as db:
            row = db.execute(
                "SELECT session_id FROM demo_accounts WHERE id=?", (body.account_id,)
            ).fetchone()
            sid = row["session_id"] if row else create(db, body.account_id)
            db.execute(
                "DELETE FROM tickets WHERE hash=? AND session_id IN (SELECT session_id FROM demo_accounts)",
                (storage.digest(request.cookies.get(cookie, "")),),
            )
            return ticket(db, request, response, sid, "parent")

    @router.get("/demo/profile", response_model=Profile)
    def profile(request: Request):
        with storage.transaction() as db:
            account = require_account(db, request, member)
            events = db.execute(
                "SELECT source_order,skill,correct,original_time FROM demo_history WHERE learner=? ORDER BY source_order",
                (account["learner"],),
            )
            return {
                **info(account["id"]),
                **json.loads(account["baseline"]),
                "account_id": account["id"],
                "session_id": account["session_id"],
                "learner_id": account["learner"],
                "history": [{**dict(e), "correct": bool(e["correct"])} for e in events],
            }

    @router.post("/demo/reset", response_model=contracts.Session)
    def reset(body: Reset, request: Request, response: Response):
        with storage.transaction(True) as db:
            account = require_account(db, request, member)
            if account["session_id"] != body.session_id:
                raise HTTPException(409, "账号或记录已切换，请刷新后重试。")
            abandoned = remove(db, account)
            sid = create(db, account["id"])
            session = ticket(db, request, response, sid, "parent")
        for cid in abandoned:
            (storage.runtime() / "photos" / (cid + ".jpg")).unlink(missing_ok=True)
        return session

    @router.post("/demo/logout", status_code=204)
    def logout(request: Request):
        with storage.transaction(True) as db:
            require_account(db, request, member)
            db.execute(
                "DELETE FROM tickets WHERE hash=?",
                (storage.digest(request.cookies.get(cookie, "")),),
            )
        response = Response(status_code=204)
        response.delete_cookie(cookie, path="/")
        return response

    @router.get("/federated")
    def federated():
        path = storage.ROOT / "artifacts/federated/report.json"
        if not path.is_file():
            raise HTTPException(503, "真实联邦训练报告尚未安装。")
        from fastapi.responses import FileResponse

        return FileResponse(path, media_type="application/json")

    return router
