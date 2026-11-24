"""Contract checks with isolated storage and explicitly synthetic provider fixtures."""

import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from apps.api import storage, vision, worker
from apps.api.main import app
from scripts.verify_phone import retained_photo_matches, verify


def jpeg(color="white", exif=None):
    out = io.BytesIO()
    Image.new("RGB", (420, 330), color).save(out, "JPEG", exif=exif or b"")
    return out.getvalue()


def item(q="2+3", s="4", ref="5", verdict="incorrect"):
    return {
        "question": q,
        "student_answer": s,
        "reference_answer": ref,
        "skill": "mixed_arithmetic",
        "verdict": verdict,
        "hints": ["先看个位。"],
        "explanation": "2 加 3 等于 5。",
        "review_reason": "",
    }


def fixture_grade(photo):
    return vision.Grade(
        items=[item(s="5", verdict="correct"), item(q="5+4", s="7", ref="9")]
    ), {
        "provider": "fixture",
        "model": "contract-fixture",
        "request_id": "fixture-only",
        "usage": {},
    }


def upload(
    phone, sid, key="capture-number-one", photo=None, source="camera", tap_side=None
):
    return phone.post(
        f"/api/v1/sessions/{sid}/captures",
        data={
            "idem": key,
            "source": source,
            "phone_confirmed": "false",
            **({"tap_side": tap_side} if tap_side else {}),
        },
        files={"photo": ("page.jpg", photo or jpeg(), "image/jpeg")},
    )


def test_double_tap_source_retry_and_quiet_mode(desks):
    parent, phone, sid = desks
    sent = upload(phone, sid, source="double_tap", tap_side="left")
    assert sent.status_code == 202
    assert sent.json()["tap_side"] == "left"
    assert (
        upload(phone, sid, source="double_tap", tap_side="left").json() == sent.json()
    )
    assert upload(phone, sid, source="double_tap", tap_side="right").status_code == 409
    assert upload(phone, sid, source="double_tap").status_code == 422
    assert upload(phone, sid, source="camera", tap_side="left").status_code == 422
    assert upload(phone, sid, source="gesture").status_code == 422
    parent.patch(f"/api/v1/sessions/{sid}/settings", json={"silent": True})
    assert (
        upload(phone, sid, key="quiet-tap-02", source="double_tap").status_code == 403
    )
    with storage.transaction() as db:
        rows = db.execute(
            "SELECT id,source,tap_side FROM captures WHERE session_id=?", (sid,)
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            (sent.json()["capture_id"], "double_tap", "left")
        ]


def test_persistence_and_idempotency(desks):
    parent, phone, sid = desks
    with parent.websocket_connect(f"/api/v1/sessions/{sid}/ws") as ws:
        r = upload(phone, sid)
        assert r.status_code == 202, r.text
        assert ws.receive_json()["type"] == "capture.received"
        assert upload(phone, sid).json() == r.json()
        assert upload(phone, sid, photo=jpeg("blue")).status_code == 409
        assert worker.run_one(fixture_grade)
        assert ws.receive_json()["type"] == "grading.running"
        assert ws.receive_json()["type"] == "grading.completed"
    jid = r.json()["job_id"]
    got = parent.get(f"/api/v1/jobs/{jid}").json()
    assert (
        got["result"][1]["verdict"] == "incorrect"
        and got["result"][1]["verification"] == "sympy"
    )
    assert len(parent.get(f"/api/v1/sessions/{sid}/homework").json()) == 1
    assert (
        parent.get("/api/v1/captures/" + r.json()["capture_id"] + "/photo").status_code
        == 200
    )
    assert (
        parent.post(
            f"/api/v1/jobs/{jid}/seen", json={"view_id": "visible-view-1"}
        ).status_code
        == 204
    )
    with storage.transaction() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 2
    assert not worker.run_one(fixture_grade)
    with pytest.raises(SystemExit, match="M1 pending"):
        verify(sid)


def test_retry_after_provider_failure(desks):
    parent, phone, sid = desks
    jid = upload(phone, sid).json()["job_id"]

    def fail(_):
        raise vision.ProviderFailure("offline fixture")

    assert worker.run_one(fail)
    assert parent.get("/api/v1/jobs/" + jid).json()["status"] == "failed"
    for _ in range(2):
        assert parent.post("/api/v1/jobs/" + jid + "/retry").status_code == 200
    assert worker.run_one(fixture_grade)
    assert parent.get("/api/v1/jobs/" + jid).json()["status"] == "completed"
    assert not worker.run_one(fixture_grade)


def test_privacy_roles_and_foreign_room(desks):
    parent, phone, sid = desks
    path = f"/api/v1/sessions/{sid}/settings"
    assert phone.patch(path, json={"silent": True}).status_code == 403
    assert (
        parent.patch(
            path, json={"silent": True}, headers={"Origin": "https://other.invalid"}
        ).status_code
        == 403
    )
    assert parent.patch(path, json={"silent": True}).status_code == 200
    assert upload(phone, sid).status_code == 403
    assert phone.get(f"/api/v1/sessions/{sid}/homework").status_code == 403
    assert phone.get(f"/api/v1/sessions/{sid}/events").json()[0]["payload"]["silent"]
    assert parent.patch(path, json={"silent": False}).status_code == 200
    assert upload(phone, sid, photo=b"invalid image").status_code == 422
    assert phone.get("/api/v1/sessions/foreign/snapshot").status_code == 403


def test_lease_recovery(desks):
    _, phone, sid = desks
    jid = upload(phone, sid).json()["job_id"]
    with storage.transaction(True) as db:
        db.execute(
            "UPDATE jobs SET status='running',lease='crashed',lease_until=0 WHERE id=?",
            (jid,),
        )
    assert worker.run_one(fixture_grade)


def test_image_orientation_and_metadata():
    exif = Image.Exif()
    exif[274] = 6
    exif[272] = "iPhone 16 Pro Max"
    exif[315] = "private author"
    result, model = vision.normalize_photo(jpeg(exif=exif))
    with Image.open(io.BytesIO(result)) as im:
        assert im.size == (330, 420)
        assert len(im.getexif()) == 0
    assert model == "iPhone 16 Pro Max"


def test_symbolic_agreement_conflict_and_missing():
    grade = vision.Grade(
        items=[item(s="4", verdict="correct"), item(q="Find the area of this shape")]
    )
    verified = worker.check_items(grade)
    assert verified[0]["verdict"] == "needs_review"
    assert verified[1]["verification"] == "visual"
    assert worker.numeric("1/0") is None
    assert worker.numeric("0.1 + 0.2") == worker.numeric("0.3")


@pytest.mark.parametrize("primary_ok", [True, False])
def test_real_wire_shape_with_mock_transport(monkeypatch, primary_ok):
    monkeypatch.setattr(
        vision,
        "config",
        lambda: [
            ("OpenAI", "https://primary.invalid/responses", "primary", "test"),
            ("DeepSeek", "https://backup.invalid/chat/completions", "backup", "test"),
        ],
    )
    calls = []

    def handle(req):
        calls.append(req.url.host)
        body = json.loads(req.content)
        result = json.dumps({"items": [item()]})
        if req.url.host == "primary.invalid":
            assert body["input"][0]["content"][0]["image_url"].startswith(
                "data:image/jpeg;base64,"
            )
            if not primary_ok:
                return httpx.Response(429)
            return httpx.Response(
                200,
                json={
                    "id": "test-r",
                    "status": "completed",
                    "output": [{"content": [{"type": "output_text", "text": result}]}],
                },
            )
        assert body["messages"][1]["content"][0]["image_url"]["url"].startswith(
            "data:image/jpeg;base64,"
        )
        return httpx.Response(
            200, json={"id": "test-b", "choices": [{"message": {"content": result}}]}
        )

    ans, meta = vision.grade_photo(jpeg(), httpx.MockTransport(handle))
    assert len(ans.items) == 1 and meta["provider"] == (
        "OpenAI" if primary_ok else "DeepSeek"
    )
    assert len(calls) == (1 if primary_ok else 2)


def test_unreadable_is_not_mistake(desks):
    parent, phone, sid = desks
    jid = upload(phone, sid).json()["job_id"]

    def unsure(photo):
        _, meta = fixture_grade(photo)
        row = item(verdict="needs_review")
        row["review_reason"] = "字迹无法辨认"
        return vision.Grade(items=[row]), meta

    assert worker.run_one(unsure)
    assert (
        parent.get("/api/v1/jobs/" + jid).json()["result"][0]["verdict"]
        == "needs_review"
    )
    with storage.transaction() as db:
        assert db.execute("SELECT count(*) FROM attempts").fetchone()[0] == 0


def test_glasses_receive_privacy_after_many_private_events(desks):
    _, phone, sid = desks
    with storage.transaction(True) as db:
        for _ in range(110):
            storage.event(db, sid, "grading.completed", {})
        storage.event(db, sid, "session.privacy", {"silent": True})
    reply = phone.get(f"/api/v1/sessions/{sid}/events").json()
    assert [row["type"] for row in reply] == ["session.privacy"]


def test_session_restart_replay_and_duplicate_receipt(desks):
    parent, phone, sid = desks
    jid = upload(phone, sid).json()["job_id"]
    assert worker.run_one(fixture_grade)
    storage.initialize()
    events = parent.get(f"/api/v1/sessions/{sid}/events?after=1").json()
    assert [event["type"] for event in events] == [
        "grading.running",
        "grading.completed",
        "mastery.updated",
        "recommendations.ready",
    ]
    for _ in range(2):
        assert (
            parent.post(
                f"/api/v1/jobs/{jid}/seen", json={"view_id": "same-parent-view"}
            ).status_code
            == 204
        )
    with storage.transaction() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM receipts WHERE job_id=?", (jid,)
            ).fetchone()[0]
            == 1
        )


def test_remote_device_cannot_create_room(desks):
    with TestClient(app, base_url="https://192.168.1.2") as remote:
        assert remote.post("/api/v1/sessions", json={}).status_code == 403


def test_rotated_native_heic_is_oriented_once():
    image = Image.new("RGB", (480, 330), "white")
    exif = image.getexif()
    exif[274] = 6
    exif[272] = "iPhone 16 Pro Max"
    image.info["exif"] = exif.tobytes()
    encoded = io.BytesIO()
    image.save(encoded, format="HEIF")
    result, camera_model = vision.normalize_photo(encoded.getvalue())
    with Image.open(io.BytesIO(result)) as normalized:
        assert normalized.format == "JPEG"
        assert normalized.size == (330, 480)
        assert not normalized.getexif()
    assert camera_model == "iPhone 16 Pro Max"


def test_retained_original_must_match_upload_digest(desks):
    _, phone, sid = desks
    cid = upload(phone, sid).json()["capture_id"]
    with storage.transaction() as db:
        sha = db.execute("SELECT sha FROM captures WHERE id=?", (cid,)).fetchone()[0]
    assert retained_photo_matches(cid, sha)
    photo = storage.runtime() / "photos" / (cid + ".jpg")
    photo.write_bytes(b"replacement inside the isolated test directory")
    assert not retained_photo_matches(cid, sha)
    photo.unlink()
    assert not retained_photo_matches(cid, sha)


def test_backup_retries_invalid_json_once(monkeypatch):
    monkeypatch.setattr(
        vision,
        "config",
        lambda: [
            ("DeepSeek", "https://backup.invalid/chat/completions", "backup", "test")
        ],
    )
    calls = []

    def reply(request):
        calls.append(json.loads(request.content))
        result = {"rows": []} if len(calls) == 1 else {"items": [item()]}
        return httpx.Response(
            200,
            json={
                "id": "fixture",
                "choices": [{"message": {"content": json.dumps(result)}}],
            },
        )

    grade, _ = vision.grade_photo(jpeg(), httpx.MockTransport(reply))
    assert len(grade.items) == 1 and len(calls) == 2
    assert "failed validation" in calls[1]["messages"][0]["content"]
