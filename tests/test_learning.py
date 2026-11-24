"""API integration with the frozen trained DKT; image grading is a labelled unit fixture."""

from fastapi.testclient import TestClient
from test_m1 import fixture_grade, upload

from apps.api import storage, worker
from apps.api.main import app


def test_learning_loop_and_revisions(desks):
    parent, phone, sid = desks
    room = "/api/v1/sessions/" + sid
    lid = parent.get(room + "/snapshot").json()["learner_id"]
    base = "/api/v1/learners/" + lid
    initial = parent.get(base + "/mastery").json()
    assert initial["available"] and initial["device"] == "cpu"
    upload(phone, sid)
    worker.run_one(fixture_grade)
    job = parent.get(room + "/homework").json()[0]
    row = job["result"][1]
    assert row["revision"] == 0 and row["id"]
    after = parent.get(base + "/mastery").json()
    assert after != initial and sum(r["evidence_count"] for r in after["skills"]) == 2
    archive = base + "/mistakes/" + row["id"]
    for _ in range(2):
        assert parent.put(archive).status_code == 200
    assert (
        len(parent.get(base + "/mistakes?skill=mixed_arithmetic").json()["items"]) == 1
    )
    assert not parent.get(base + "/mistakes?skill=area").json()["items"]
    path = "/api/v1/questions/" + row["id"] + "/review"
    fix = {"question": row["question"], "student_answer": "9", "revision": 0}
    assert parent.patch(path, json=fix).json()["verdict"] == "correct"
    assert parent.patch(path, json=fix).status_code == 409
    assert parent.get(room + "/homework").json()[0]["result"][1]["revision"] == 1
    assert parent.get(base + "/mastery").json() != after
    exercises = parent.get(base + "/recommendations").json()["items"]
    assert (
        len(exercises) == 2
        and exercises == parent.get(base + "/recommendations").json()["items"]
    )
    rid = exercises[0]["id"]
    with storage.transaction() as db:
        answer = db.execute(
            "SELECT answer FROM recommendations WHERE id=?", (rid,)
        ).fetchone()[0]
    path = "/api/v1/recommendations/" + rid + "/attempts"
    for _ in range(2):
        resp = parent.post(path, json={"answer": answer, "idem": "response-unique"})
        assert resp.json()["correct"]
    assert (
        sum(r["evidence_count"] for r in parent.get(base + "/mastery").json()["skills"])
        == 3
    )
    assert (
        parent.post(
            path, json={"answer": answer, "idem": "response-another"}
        ).status_code
        == 409
    )
    assert phone.get(base + "/mastery").status_code == 403
    with TestClient(app) as other:
        other.post("/api/v1/sessions", json={})
        assert other.get(base + "/mastery").status_code == 403
        assert (
            other.patch(
                "/api/v1/questions/" + row["id"] + "/review", json=fix
            ).status_code
            == 404
        )
    next_sid = parent.post("/api/v1/sessions", json={}).json()["session_id"]
    assert (
        parent.get("/api/v1/sessions/" + next_sid + "/snapshot").json()["learner_id"]
        == lid
    )
    assert len(parent.get(base + "/mistakes").json()["items"]) == 1
    assert (
        parent.get("/api/v1/captures/" + job["capture_id"] + "/photo").status_code
        == 200
    )


def test_original_grade_survives_migration_and_review(desks):
    import json

    parent, phone, sid = desks
    jid = upload(phone, sid).json()["job_id"]
    worker.run_one(fixture_grade)
    with storage.transaction(True) as db:
        db.execute("DELETE FROM questions")
        db.execute("PRAGMA user_version=1")
    storage.initialize()
    item = parent.get("/api/v1/jobs/" + jid).json()["result"][1]
    parent.patch(
        "/api/v1/questions/" + item["id"] + "/review",
        json={"revision": 0, "question": item["question"], "student_answer": "9"},
    )
    storage.initialize()
    with storage.transaction() as db:
        assert (
            json.loads(db.execute("SELECT result FROM jobs").fetchone()[0])[1][
                "verdict"
            ]
            == "incorrect"
        )
        assert db.execute("SELECT count(*) FROM questions").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM question_revisions").fetchone()[0] == 1
