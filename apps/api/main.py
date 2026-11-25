import asyncio
import hashlib
import io
import json
import os
import secrets
import time
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

import qrcode
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import clouclip, contracts, demo, eyecare, learning, sensors, storage
from .catalog import PRODUCTS
from .vision import MAX_BYTES, Skill, config, normalize_photo


@asynccontextmanager
async def lifespan(app):
    storage.initialize()

    async def expire_observations():
        while True:
            await asyncio.sleep(1)
            await asyncio.to_thread(clouclip.advance_all)
            await asyncio.to_thread(sensors.expire_stale)

    task = asyncio.create_task(expire_observations())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="LumiRead", version="0.1.0", lifespan=lifespan)
API = "/api/v1"
COOKIE = "lumiread_access"
DIST = storage.ROOT / "apps/web/dist"


@app.middleware("http")
async def protect(request: Request, call_next):
    if request.url.path.endswith("/captures") and request.method == "POST":
        length = request.headers.get("content-length")
        if length and length.isdecimal() and int(length) > MAX_BYTES + 65536:
            return JSONResponse({"detail": "照片过大，请选择小于 16 MB 的照片。"}, 413)
    origin = request.headers.get("origin")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin != str(request.base_url).rstrip("/")
    ):
        return JSONResponse({"detail": "来源与演示服务不一致"}, 403)
    resp = await call_next(request)
    if request.url.path.startswith(API):
        resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


def member(db, request, sid=None, roles=("parent", "glasses")):
    token = request.cookies.get(COOKIE, "")
    row = db.execute(
        "SELECT * FROM tickets WHERE hash=? AND expires>?",
        (storage.digest(token), time.time()),
    ).fetchone()
    if not row:
        raise HTTPException(401, "请先配对设备。")
    if (
        (sid and sid != row["session_id"])
        or row["role"] not in roles
        or (request.scope.get("phone_only") and row["role"] != "glasses")
    ):
        raise HTTPException(403, "此设备没有访问权限。")
    return row


def ticket(db, request, response, sid, role):
    secret = secrets.token_urlsafe(32)
    db.execute(
        "INSERT INTO tickets VALUES(?,?,?,?)",
        (storage.digest(secret), sid, role, time.time() + 86400),
    )
    response.set_cookie(
        COOKIE,
        secret,
        max_age=86400,
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {"session_id": sid, "role": role}


app.include_router(demo.make_router(member, ticket, COOKIE), prefix=API)
app.include_router(clouclip.make_router(member), prefix=API)
app.include_router(eyecare.router, prefix=API)


class CreateSession(BaseModel):
    pass


class Invitation(BaseModel):
    role: Literal["glasses", "parent"] = "glasses"


class Join(BaseModel):
    code: str = Field(min_length=6, max_length=100)


class Privacy(BaseModel):
    silent: bool


class Receipt(BaseModel):
    view_id: str = Field(min_length=8, max_length=100)


@app.get(API + "/health/ready", response_model=contracts.Readiness)
def ready():
    from ml.dkt.inference import model_info

    return {
        "api": "ready",
        "vision_configured": any(p[3] for p in config()),
        "model": model_info(),
    }


@app.post(API + "/sessions", status_code=201, response_model=contracts.Session)
def create_session(body: CreateSession, request: Request, response: Response):
    if request.client.host not in (
        "127.0.0.1",
        "::1",
        "testclient",
    ) or request.url.hostname not in ("localhost", "127.0.0.1", "::1", "testserver"):
        raise HTTPException(403, "请在演示电脑的本机入口创建场次。")
    sid = storage.uid()
    with storage.transaction(True) as db:
        try:
            old = member(db, request, roles=("parent",))
            if demo.find(db, old["session_id"]):
                return JSONResponse({"detail": "请在账号菜单切换或重置演示记录。"}, 409)
            learner = db.execute(
                "SELECT learner FROM sessions WHERE id=?", (old["session_id"],)
            ).fetchone()[0]
        except HTTPException:
            learner = storage.uid()
            db.execute("INSERT INTO learners VALUES(?)", (learner,))
        db.execute(
            "INSERT INTO sessions(id,learner,created) VALUES(?,?,?)",
            (sid, learner, time.time()),
        )
        return ticket(db, request, response, sid, "parent")


@app.get(API + "/me", response_model=contracts.Session)
def me(request: Request):
    with storage.transaction() as db:
        row = member(db, request)
        return {"session_id": row["session_id"], "role": row["role"]}


@app.get(API + "/sessions/{sid}/phone-setup", response_model=contracts.PhoneSetup)
def phone_setup(sid: str, request: Request):
    with storage.transaction() as db:
        member(db, request, sid, ("parent",))
    info = storage.runtime() / "server.json"
    if not info.is_file():
        return {"certificate": None, "fingerprint": None}
    data = json.loads(info.read_text())
    return {
        "certificate": data["ca"],
        "fingerprint": data["ca_sha256"],
        "mode": data.get("mode", "lan"),
        "public_unavailable": data.get("public_unavailable", False),
    }


@app.post(API + "/sessions/{sid}/invites", response_model=contracts.Invite)
def invite(sid: str, body: Invitation, request: Request):
    with storage.transaction(True) as db:
        member(db, request, sid, ("parent",))
        if demo.find(db, sid):
            raise HTTPException(409, "演示账号使用电脑上传作业。")
        if os.environ.get("LUMIREAD_PUBLIC_ORIGIN") and body.role == "parent":
            raise HTTPException(403, "公网入口仅用于配对拍摄设备。")
        code = secrets.token_urlsafe(12)
        db.execute(
            "INSERT INTO invites VALUES(?,?,?,?)",
            (storage.digest(code), sid, body.role, time.time() + 1800),
        )
    base = os.environ.get("LUMIREAD_PHONE_ORIGIN", str(request.base_url).rstrip("/"))
    route = "/glasses" if body.role == "glasses" else "/legacy-app"
    return {
        "url": base + route + "#" + urlencode({"room": sid, "code": code}),
        "code": code,
        "session_id": sid,
    }


@app.get(API + "/sessions/{sid}/qr")
def qr(sid: str, code: str, request: Request):
    with storage.transaction() as db:
        member(db, request, sid, ("parent",))
        row = db.execute(
            "SELECT role FROM invites WHERE hash=? AND session_id=? AND expires>?",
            (storage.digest(code), sid, time.time()),
        ).fetchone()
        if not row:
            raise HTTPException(404, "配对码已失效")
    base = os.environ.get("LUMIREAD_PHONE_ORIGIN", str(request.base_url).rstrip("/"))
    route = "/glasses" if row["role"] == "glasses" else "/legacy-app"
    target = base + route + "#" + urlencode({"room": sid, "code": code})
    out = io.BytesIO()
    qrcode.make(target).save(out, format="PNG")
    return Response(out.getvalue(), media_type="image/png")


@app.post(API + "/sessions/{sid}/join", response_model=contracts.Session)
def join(sid: str, body: Join, request: Request, response: Response):
    with storage.transaction(True) as db:
        key = storage.digest(body.code)
        row = db.execute(
            "SELECT role FROM invites WHERE hash=? AND session_id=? AND expires>?",
            (key, sid, time.time()),
        ).fetchone()
        if not row or (request.scope.get("phone_only") and row["role"] != "glasses"):
            raise HTTPException(403, "配对码无效或已使用，请重新生成。")
        db.execute("DELETE FROM invites WHERE hash=?", (key,))
        return ticket(db, request, response, sid, row["role"])


@app.get(API + "/sessions/{sid}/snapshot", response_model=contracts.Snapshot)
def snapshot(sid: str, request: Request):
    with storage.transaction() as db:
        m = member(db, request, sid)
        s = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        seq = db.execute(
            "SELECT COALESCE(MAX(seq),0) FROM events WHERE session_id=?", (sid,)
        ).fetchone()[0]
        return {
            "session_id": sid,
            "learner_id": s["learner"],
            "silent": bool(s["silent"]),
            "role": m["role"],
            "seq": seq,
        }


@app.patch(API + "/sessions/{sid}/settings", response_model=Privacy)
def settings(sid: str, body: Privacy, request: Request):
    with storage.transaction(True) as db:
        member(db, request, sid, ("parent",))
        db.execute("UPDATE sessions SET silent=? WHERE id=?", (int(body.silent), sid))
        if body.silent:
            sensors.stop(db, sid, "silent")
        storage.event(db, sid, "session.privacy", {"silent": body.silent})
    return body


def capture_access(db, request, sid, source=None):
    if source == "upload" and demo.find(db, sid):
        member(db, request, sid, ("parent",))
        return
    member(db, request, sid, ("glasses",))
    if db.execute("SELECT silent FROM sessions WHERE id=?", (sid,)).fetchone()[0]:
        raise HTTPException(403, "入校静音中，拍照已关闭。")


@app.post(
    API + "/sessions/{sid}/captures",
    status_code=202,
    response_model=contracts.CaptureReceipt,
)
def capture(
    sid: str,
    request: Request,
    photo: Annotated[UploadFile, File()],
    idem: Annotated[str, Form(min_length=8, max_length=100)],
    source: Annotated[
        Literal["camera", "native_camera", "upload", "double_tap"], Form()
    ],
    phone_confirmed: Annotated[bool, Form()] = False,
    tap_side: Annotated[Literal["left", "right"] | None, Form()] = None,
):
    with storage.transaction() as db:
        capture_access(db, request, sid, source)
    if (source == "double_tap") != (tap_side is not None):
        raise HTTPException(422, "双击抓拍需要注明左侧或右侧触控区。")
    try:
        image, model = normalize_photo(photo.file.read(MAX_BYTES + 1))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    sha = hashlib.sha256(image).hexdigest()
    cid, jid = storage.uid(), storage.uid()
    photos = storage.runtime() / "photos"
    photos.mkdir(mode=0o700, exist_ok=True)
    path = photos / (cid + ".jpg")
    try:
        with storage.transaction(True) as db:
            capture_access(db, request, sid, source)
            old = db.execute(
                """SELECT c.id,j.id AS job,c.sha,c.source,c.tap_side FROM captures c JOIN jobs j ON j.capture_id=c.id
                WHERE c.session_id=? AND c.idem=?""",
                (sid, idem),
            ).fetchone()
            if old:
                if (
                    old["sha"] != sha
                    or old["source"] != source
                    or old["tap_side"] != tap_side
                ):
                    raise HTTPException(409, "上传编号已用于另一张照片。")
                return {
                    "capture_id": old["id"],
                    "job_id": old["job"],
                    "tap_side": old["tap_side"],
                }
            path.write_bytes(image)
            db.execute(
                """INSERT INTO captures(id,session_id,idem,sha,source,user_agent,phone_confirmed,camera_model,created,tap_side)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    cid,
                    sid,
                    idem,
                    sha,
                    source,
                    request.headers.get("user-agent", "")[:400],
                    int(phone_confirmed),
                    model,
                    time.time(),
                    tap_side,
                ),
            )
            db.execute(
                "INSERT INTO jobs(id,capture_id,status) VALUES(?,?,'queued')",
                (jid, cid),
            )
            storage.event(
                db, sid, "capture.received", {"job_id": jid, "capture_id": cid}
            )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {"capture_id": cid, "job_id": jid, "tap_side": tap_side}


def serialize(db, row):
    values = dict(row)
    for key in ("result", "usage"):
        values[key] = json.loads(values[key]) if values[key] else None
    if row["status"] == "completed":
        values["result"] = learning.current_results(db, row["id"])
    return values


QUERY = """SELECT j.id,j.capture_id,j.status,j.error,j.result,j.model,j.provider,j.request_id,j.usage,j.latency,
    c.created,c.session_id FROM jobs j JOIN captures c ON c.id=j.capture_id"""


@app.get(API + "/sessions/{sid}/homework", response_model=list[contracts.Job])
def homework(sid: str, request: Request):
    with storage.transaction() as db:
        member(db, request, sid, ("parent",))
        return [
            serialize(db, row)
            for row in db.execute(
                QUERY + " WHERE c.session_id=? ORDER BY c.created DESC", (sid,)
            )
        ]


@app.get(API + "/jobs/{jid}", response_model=contracts.Job)
def job(jid: str, request: Request):
    with storage.transaction() as db:
        m = member(db, request, roles=("parent",))
        row = db.execute(
            QUERY + " WHERE j.id=? AND c.session_id=?", (jid, m["session_id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "找不到任务")
        return serialize(db, row)


@app.get(API + "/captures/{cid}/photo")
def original(cid: str, request: Request):
    with storage.transaction() as db:
        m = member(db, request, roles=("parent",))
        if not db.execute(
            """SELECT 1 FROM captures c JOIN sessions s ON s.id=c.session_id
               WHERE c.id=? AND s.learner=(SELECT learner FROM sessions WHERE id=?)""",
            (cid, m["session_id"]),
        ).fetchone():
            raise HTTPException(404, "找不到照片")
    return FileResponse(
        storage.runtime() / "photos" / (cid + ".jpg"), media_type="image/jpeg"
    )


@app.post(API + "/jobs/{jid}/retry", response_model=contracts.JobId)
def retry(jid: str, request: Request):
    with storage.transaction(True) as db:
        m = member(db, request, roles=("parent",))
        row = db.execute(
            QUERY + " WHERE j.id=? AND c.session_id=?", (jid, m["session_id"])
        ).fetchone()
        if not row:
            raise HTTPException(404, "找不到任务")
        if row["status"] == "failed":
            db.execute("UPDATE jobs SET status='queued',error=NULL WHERE id=?", (jid,))
            storage.event(db, row["session_id"], "grading.queued", {"job_id": jid})
        return {"job_id": jid}


@app.post(API + "/jobs/{jid}/seen", status_code=204)
def seen(jid: str, body: Receipt, request: Request):
    with storage.transaction(True) as db:
        m = member(db, request, roles=("parent",))
        if not db.execute(
            QUERY + " WHERE j.id=? AND c.session_id=? AND j.status='completed'",
            (jid, m["session_id"]),
        ).fetchone():
            raise HTTPException(404, "找不到已完成的作业")
        db.execute(
            "INSERT OR IGNORE INTO receipts VALUES(?,?,?)",
            (jid, body.view_id, time.time()),
        )
    return Response(status_code=204)


def events_since(db, sid, after, role):
    rows = db.execute(
        """SELECT * FROM events WHERE session_id=? AND seq>?
        AND (?='parent' OR kind IN ('session.privacy','alert.raised','alert.cleared')) ORDER BY seq LIMIT 100""",
        (sid, after, role),
    ).fetchall()
    return [
        {
            "event_id": f"{sid}.{r['seq']}",
            "session_id": sid,
            "seq": r["seq"],
            "type": r["kind"],
            "occurred_at": datetime.fromtimestamp(r["ts"], UTC).isoformat(),
            "payload": json.loads(r["payload"]),
        }
        for r in rows
    ]


@app.get(API + "/sessions/{sid}/events", response_model=list[contracts.Event])
def events(sid: str, request: Request, after: int = 0):
    with storage.transaction() as db:
        m = member(db, request, sid)
        return events_since(db, sid, after, m["role"])


@app.websocket(API + "/sessions/{sid}/ws")
async def ws(socket: WebSocket, sid: str, after: int = 0):
    origin = socket.headers.get("origin")
    if origin and urlsplit(origin).netloc != socket.headers.get("host"):
        await socket.close(code=1008)
        return
    try:
        with storage.transaction() as db:
            member(db, socket, sid)
    except HTTPException:
        await socket.close(code=1008)
        return
    await socket.accept()
    try:
        while True:
            with storage.transaction() as db:
                m = member(db, socket, sid)
                rows = events_since(db, sid, after, m["role"])
            for row in rows:
                await socket.send_json(row)
                after = row["seq"]
            try:
                await asyncio.wait_for(socket.receive_text(), timeout=0.25)
            except TimeoutError:
                pass
    except (WebSocketDisconnect, RuntimeError, HTTPException):
        return


@app.get(API + "/products", response_model=contracts.Catalog)
def catalog():
    return {"products": PRODUCTS, "subscription_cny": 198, "assistant_path": "/app"}


def parent_learner(db, request, learner=None):
    ticket = member(db, request, roles=("parent",))
    actual = db.execute(
        "SELECT learner FROM sessions WHERE id=?", (ticket["session_id"],)
    ).fetchone()[0]
    if learner and learner != actual:
        raise HTTPException(403, "无权访问该学习记录")
    return actual


@app.get(API + "/learners/{lid}/mastery", response_model=contracts.Mastery)
def learner_mastery(lid: str, request: Request):
    with storage.transaction() as db:
        parent_learner(db, request, lid)
        records = learning.history(db, lid)
    return learning.mastery(records)


@app.get(API + "/learners/{lid}/recommendations", response_model=contracts.Exercises)
def recommendations(lid: str, request: Request):
    with storage.transaction(True) as db:
        parent_learner(db, request, lid)
        return {"items": learning.recommend(db, lid)}


@app.post(
    API + "/recommendations/{rid}/attempts", response_model=contracts.PracticeResult
)
def practice(rid: str, body: contracts.PracticeAnswer, request: Request):
    with storage.transaction(True) as db:
        return learning.practice_answer(
            db, parent_learner(db, request), rid, body.answer.strip(), body.idem
        )


@app.put(API + "/learners/{lid}/mistakes/{qid}", response_model=contracts.Mistake)
def archive(lid: str, qid: str, request: Request):
    with storage.transaction(True) as db:
        parent_learner(db, request, lid)
        row = db.execute(learning.QUESTION, (qid, lid)).fetchone()
        if not row:
            raise HTTPException(404, "题目不存在")
        item = learning.result(row)
        saved = db.execute(
            "SELECT created FROM mistakes WHERE question_id=? AND learner=?", (qid, lid)
        ).fetchone()
        if not saved:
            if item["verdict"] != "incorrect":
                raise HTTPException(409, "请选择已判定的错题。")
            created = time.time()
            db.execute("INSERT INTO mistakes VALUES(?,?,?)", (lid, qid, created))
            storage.event(db, row["session_id"], "mistake.saved", {"question_id": qid})
        else:
            created = saved["created"]
        return {**item, "capture_id": row["capture_id"], "created": created}


@app.get(API + "/learners/{lid}/mistakes", response_model=contracts.Mistakes)
def mistakes(lid: str, request: Request, skill: Skill | None = None):
    with storage.transaction() as db:
        parent_learner(db, request, lid)
        rows = db.execute(
            """SELECT q.*,j.capture_id,m.created FROM mistakes m JOIN questions q
                           ON q.id=m.question_id JOIN jobs j ON j.id=q.job_id WHERE m.learner=?
                           AND (? IS NULL OR json_extract(q.result,'$.skill')=?) ORDER BY m.created DESC""",
            (lid, skill, skill),
        )
        return {
            "items": [
                {
                    **learning.result(r),
                    "capture_id": r["capture_id"],
                    "created": r["created"],
                }
                for r in rows
            ]
        }


@app.patch(API + "/questions/{qid}/review", response_model=contracts.QuestionResult)
def review(qid: str, body: contracts.Review, request: Request):
    from . import vision, worker

    with storage.transaction() as db:
        learner = parent_learner(db, request)
        row = db.execute(learning.QUESTION, (qid, learner)).fetchone()
        if not row:
            raise HTTPException(404, "题目不存在")
        if row["revision"] != body.revision:
            raise HTTPException(409, "题目已更新，请刷新后重新核对。")
    question, answer = body.question.strip(), body.student_answer.strip()
    if not question or not answer:
        raise HTTPException(422, "请完整填写题目和作答。")
    expected, student = worker.numeric(question), worker.numeric(answer)
    original_item = json.loads(row["result"])
    if (
        expected is not None
        and student is not None
        and question == original_item["question"]
        and worker.numeric(original_item["reference_answer"]) == expected
    ):
        item = {
            **original_item,
            "student_answer": answer,
            "reference_answer": str(expected),
            "verification": "sympy",
            "review_reason": "",
            "verdict": "correct" if expected == student else "incorrect",
        }
        if item["verdict"] == "incorrect" and not item["hints"]:
            item["hints"] = [
                f"观察 {question}，按照运算顺序应先算哪一部分？",
                "可以逐步写出中间结果，再与自己的答案比较。",
            ]
        receipt = {"method": "sympy"}
    else:
        try:
            photo = (
                storage.runtime() / "photos" / (row["capture_id"] + ".jpg")
            ).read_bytes()
            grade, receipt = vision.grade_photo(
                photo, correction=(row["ordinal"], question, answer)
            )
        except (vision.ProviderFailure, OSError) as exc:
            raise HTTPException(
                503, "此次复核未完成，保留上次判分，请稍后重试。"
            ) from exc
        if len(grade.items) != 1:
            raise HTTPException(502, "未返回唯一的复核题目，请再试一次。")
        corrected = grade.items[0].model_copy(
            update={"question": question, "student_answer": answer}
        )
        item = worker.check_items(vision.Grade(items=[corrected]))[0]
    with storage.transaction(True) as db:
        parent_learner(db, request, learner)
        return learning.reviewed(db, row, item, receipt)


@app.post(API + "/sessions/{sid}/telemetry/batch", response_model=contracts.Received)
def telemetry_batch(sid: str, body: sensors.Batch, request: Request):
    with storage.transaction(True) as db:
        capture_access(db, request, sid)
        transport = (
            "public_https"
            if request.scope.get("phone_only")
            else ("lan_https" if request.url.scheme == "https" else "local")
        )
        return sensors.ingest(
            db,
            sid,
            body.samples,
            transport,
            "iPhone" in request.headers.get("user-agent", ""),
        )


@app.get(API + "/sessions/{sid}/telemetry", response_model=contracts.Samples)
def telemetry(sid: str, request: Request, limit: int = Query(300, ge=1, le=2000)):
    with storage.transaction() as db:
        member(db, request, sid, ("parent",))
        rows = db.execute(
            "SELECT body FROM telemetry WHERE session_id=? ORDER BY observed DESC,id DESC LIMIT ?",
            (sid, limit),
        )
        return {"samples": [json.loads(r["body"]) for r in rows]}


@app.get(API + "/sessions/{sid}/alerts", response_model=contracts.Alerts)
def alerts(sid: str, request: Request):
    with storage.transaction() as db:
        member(db, request, sid)
        rows = db.execute(
            "SELECT * FROM alerts WHERE session_id=? ORDER BY (ended IS NULL) DESC,raised DESC LIMIT 100",
            (sid,),
        )
        return {"alerts": [sensors.alert(r) for r in rows]}


@app.post(API + "/sessions/{sid}/alerts/{aid}/seen", status_code=204)
def alert_seen(sid: str, aid: str, request: Request):
    with storage.transaction(True) as db:
        member(db, request, sid, ("parent",))
        if not db.execute(
            "UPDATE alerts SET seen=COALESCE(seen,?) WHERE id=? AND session_id=?",
            (time.time(), aid, sid),
        ).rowcount:
            raise HTTPException(404, "提醒不存在")
    return Response(status_code=204)


@app.get("/eye-care")
@app.get("/showcase")
@app.get("/legacy-app")
@app.get("/federated")
@app.get("/app")
@app.get("/glasses")
@app.get("/")
def web():
    if not (DIST / "index.html").is_file():
        raise HTTPException(503, "请先构建 Web 前端")
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})


app.mount(
    "/assets", StaticFiles(directory=DIST / "assets", check_dir=False), name="assets"
)

for folder in ("products", "vision"):
    app.mount(
        "/" + folder, StaticFiles(directory=DIST / folder, check_dir=False), name=folder
    )
