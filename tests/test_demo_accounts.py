import pytest
from fastapi.testclient import TestClient
from test_m1 import fixture_grade, jpeg

from apps.api import demo, learning, storage, worker
from apps.api.main import app


def login(client, account):
    response = client.post("/api/v1/demo/login", json={"account_id": account})
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


@pytest.fixture
def browser(tmp_path, monkeypatch):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path / "run"))
    # Tests also work in a redistributed archive before downloading student rows.
    import json

    rows = [
        {
            "id": k,
            "split": "validation",
            "learner_hash": "fixture-" + k,
            "events": [
                {
                    "problem_log_id": 1000 + i,
                    "skill": "fractions",
                    "correct": bool(i % 2),
                    "observed_at": None,
                }
                for i in range(n)
            ],
        }
        for k, n in zip("ABC", (4, 17, 77))
    ]
    p = tmp_path / "seed.json"
    p.write_text(json.dumps({"accounts": rows}))
    monkeypatch.setattr(demo, "SEEDS", p)
    with TestClient(app) as client:
        yield client


def test_isolation_reload_revision_and_reset(browser):
    snapshots = {}
    for k in "ABC":
        sid = login(browser, k)
        profile = browser.get("/api/v1/demo/profile").json()
        assert profile["account_id"] == k and profile["session_id"] == sid
        lid = profile["learner_id"]
        base = browser.get(f"/api/v1/learners/{lid}/mastery").json()
        assert base["available"] and len(base["skills"]) == 6
        records = [(e["skill"], e["correct"]) for e in profile["history"]]
        assert base == learning.mastery(records)
        snapshots[k] = sid, lid, base
    sid, lid, base = snapshots["B"]
    assert login(browser, "B") == sid
    path = f"/api/v1/sessions/{sid}/captures"

    def upload():
        return browser.post(
            path,
            data={"idem": "demo-persistent-upload", "source": "upload"},
            files={"photo": ("page.png", jpeg(), "image/jpeg")},
        )

    accepted = upload()
    assert accepted.status_code == 202 and upload().json() == accepted.json()
    assert worker.run_one(fixture_grade)
    jid, cid = accepted.json()["job_id"], accepted.json()["capture_id"]
    job = browser.get("/api/v1/jobs/" + jid).json()
    assert len(job["result"]) == 2
    item = job["result"][1]
    qid = item["id"]
    assert browser.put(f"/api/v1/learners/{lid}/mistakes/{qid}").is_success

    def count():
        return sum(
            s["evidence_count"]
            for s in browser.get(f"/api/v1/learners/{lid}/mastery").json()["skills"]
        )

    n = count()
    assert n == 19
    assert browser.patch(
        "/api/v1/questions/" + qid + "/review",
        json={
            "revision": 0,
            "question": item["question"],
            "student_answer": item["reference_answer"],
        },
    ).is_success
    assert count() == n
    items = browser.get(f"/api/v1/learners/{lid}/recommendations").json()["items"]
    assert len(items) == 2
    assert browser.post(
        "/api/v1/recommendations/" + items[0]["id"] + "/attempts",
        json={"answer": "0", "idem": "practice-demo-one"},
    ).is_success
    assert count() == n + 1
    for k in "AC":
        other, other_lid, other_profile = snapshots[k]
        assert login(browser, k) == other
        assert (
            browser.get(f"/api/v1/learners/{other_lid}/mastery").json() == other_profile
        )
        assert browser.get(f"/api/v1/sessions/{other}/homework").json() == []
        assert browser.get(f"/api/v1/sessions/{sid}/homework").status_code == 403
        assert browser.get(f"/api/v1/learners/{lid}/mistakes").status_code == 403
        assert browser.get(f"/api/v1/captures/{cid}/photo").status_code == 404
        assert (
            browser.post("/api/v1/demo/reset", json={"session_id": sid}).status_code
            == 409
        )
    assert login(browser, "B") == sid
    assert count() == n + 1
    assert browser.get(f"/api/v1/jobs/{jid}").is_success
    with TestClient(app) as second:
        login(second, "B")
        reset = browser.post("/api/v1/demo/reset", json={"session_id": sid})
        assert reset.is_success and reset.json()["session_id"] != sid
        assert second.get("/api/v1/demo/profile").status_code == 401
    now = browser.get("/api/v1/demo/profile").json()
    assert browser.get(f"/api/v1/learners/{now['learner_id']}/mastery").json() == base
    assert browser.get(f"/api/v1/sessions/{now['session_id']}/homework").json() == []
    assert not (storage.runtime() / "photos" / (cid + ".jpg")).exists()
    assert browser.post("/api/v1/demo/logout").status_code == 204
    assert browser.get("/api/v1/demo/profile").status_code == 401
