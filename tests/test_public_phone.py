"""Phone-only public surface and local host share the same real pairing flow."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from test_m1 import upload

from apps.api.main import app
from apps.api.phone import gateway

ORIGIN = "https://test-phone.trycloudflare.com"


def test_public_camera(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    monkeypatch.setenv("LUMIREAD_PHONE_ORIGIN", ORIGIN)
    monkeypatch.setenv("LUMIREAD_PUBLIC_ORIGIN", ORIGIN)
    headers = {"X-Forwarded-Proto": "https", "Origin": ORIGIN}
    with (
        TestClient(app) as parent,
        TestClient(gateway, base_url=ORIGIN, headers=headers) as camera,
    ):
        sid = parent.post("/api/v1/sessions", json={}).json()["session_id"]
        room = "/api/v1/sessions/" + sid
        inv = parent.post(room + "/invites", json={}).json()
        assert inv["url"].startswith(ORIGIN + "/glasses#")
        assert camera.get("/glasses").status_code == 200
        assert camera.get("/app").status_code == 404
        assert camera.post("/api/v1/sessions", json={}).status_code == 404
        assert camera.get(room + "/homework").status_code == 404
        assert camera.get("/openapi.json").status_code == 404
        assert (
            camera.get("/glasses", headers={"X-Forwarded-Proto": "http"}).status_code
            == 403
        )
        assert upload(camera, sid).status_code == 401
        assert (
            camera.post(
                room + "/join",
                headers={"Origin": "https://elsewhere.example"},
                json={"code": inv["code"]},
            ).status_code
            == 403
        )
        found = camera.post(room + "/join", json={"code": inv["code"]})
        assert found.json()["role"] == "glasses"
        assert "Secure" in found.headers["set-cookie"]
        assert (
            camera.post(room + "/join", json={"code": inv["code"]}).status_code == 403
        )
        assert camera.get("/api/v1/me").json()["session_id"] == sid
        with parent.websocket_connect(room + "/ws") as parentsocket:
            assert upload(camera, sid).status_code == 202
            assert parentsocket.receive_json()["type"] == "capture.received"
        with camera.websocket_connect(
            ORIGIN.replace("https:", "wss:") + room + "/ws"
        ) as ws:
            parent.patch(room + "/settings", json={"silent": True})
            assert ws.receive_json()["type"] == "session.privacy"
        assert upload(camera, sid).status_code == 403

        camera.cookies.clear()
        camera.cookies.set("lumiread_access", parent.cookies.get("lumiread_access"))
        assert camera.get(room + "/snapshot").status_code == 403
        with (
            pytest.raises(WebSocketDisconnect),
            camera.websocket_connect(ORIGIN.replace("https:", "wss:") + room + "/ws"),
        ):
            pass
