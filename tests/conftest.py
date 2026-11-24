import pytest
from fastapi.testclient import TestClient

from apps.api import storage
from apps.api.main import app


@pytest.fixture
def desks(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    storage.initialize()
    with TestClient(app) as parent, TestClient(app) as phone:
        sid = parent.post("/api/v1/sessions", json={}).json()["session_id"]
        invite = parent.post(f"/api/v1/sessions/{sid}/invites", json={}).json()
        body = {"code": invite["code"]}
        assert phone.post(f"/api/v1/sessions/{sid}/join", json=body).status_code == 200
        assert phone.post(f"/api/v1/sessions/{sid}/join", json=body).status_code == 403
        yield parent, phone, sid
