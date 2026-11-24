from datetime import UTC, datetime, timedelta


def test_thresholds_replay_and_sources(desks):
    parent, phone, sid = desks
    room = "/api/v1/sessions/" + sid
    now = datetime.now(UTC)

    def sample(second, value):
        return {
            "metric": "distance_cm",
            "unit": "cm",
            "value_kind": "estimated",
            "input_mode": "live",
            "value": value,
            "observed_at": (now + timedelta(seconds=second)).isoformat(),
            "quality": "ok" if value is not None else "missing",
            "method": "qr-size-proxy-v2",
            "calibration_id": None,
        }

    def send(*rows):
        return phone.post(room + "/telemetry/batch", json={"samples": list(rows)})

    assert not send(sample(0, 24)).json()["active_alerts"]
    batch = [sample(1, 28), sample(2, 27), sample(3, 28), sample(4, 34)]
    r = send(*batch).json()
    assert len(r["active_alerts"]) == 1 and r["accepted"] == 4
    assert send(*batch).json()["accepted"] == 0
    aid = r["active_alerts"][0]["id"]
    assert parent.post(room + "/alerts/" + aid + "/seen").status_code == 204
    assert send(sample(5, 36)).json()["active_alerts"] == []
    send(sample(6, 26), sample(8, 27), sample(9, None))
    rows = parent.get(room + "/alerts").json()["alerts"]
    assert [r["reason"] for r in rows] == ["signal_lost", "returned_to_range"]
    simulated = {
        "metric": "reading_seconds",
        "unit": "s",
        "method": "demo-clock-300x-v1",
        "quality": "ok",
        "value_kind": "simulated",
        "input_mode": "accelerated",
        "value": 2700,
        "observed_at": now.isoformat(),
    }
    assert send(simulated).json()["active_alerts"][0]["input_mode"] == "accelerated"
    assert send({**simulated, "input_mode": "live"}).status_code == 422
    parent.patch(room + "/settings", json={"silent": True})
    assert parent.get(room + "/alerts").json()["alerts"][0]["reason"] == "silent"
    assert send(sample(10, 40)).status_code == 403
    assert phone.get(room + "/telemetry").status_code == 403
    events = phone.get(room + "/events").json()
    assert {r["type"] for r in events} == {
        "alert.raised",
        "alert.cleared",
        "session.privacy",
    }
    assert parent.get(room + "/telemetry?limit=1").json()["samples"][0]["value"] is None


def test_catalog_is_public_and_independent(desks):
    _, phone, _ = desks
    catalog = phone.get("/api/v1/products").json()
    assert [p["price_cny"] for p in catalog["products"]] == [799, 499]
    assert catalog["products"][1]["weight_g"] == 13
    assert all(len(p["hotspots"]) == 3 for p in catalog["products"])
    assert "session" not in catalog


def test_new_camera_rejects_face_telemetry_but_can_read_history(desks):
    from apps.api import sensors, storage

    parent, phone, sid = desks
    path = f"/api/v1/sessions/{sid}/telemetry"
    sample = sensors.Sample(
        metric="head_tilt_deg",
        unit="deg",
        value=1,
        value_kind="estimated",
        input_mode="live",
        method="eye-line-roll-v1",
        quality="ok",
        observed_at=datetime.now(UTC),
    )
    with storage.transaction(True) as db:
        sensors.ingest(db, sid, [sample])
    assert (
        phone.post(
            path + "/batch", json={"samples": [sample.model_dump(mode="json")]}
        ).status_code
        == 422
    )
    assert [s["metric"] for s in parent.get(path).json()["samples"]] == [
        "head_tilt_deg"
    ]


def test_lost_camera_closes_alert_and_marks_last_sample_missing(desks):
    from apps.api import sensors

    parent, phone, sid = desks
    room = "/api/v1/sessions/" + sid
    now = datetime.now(UTC)
    samples = [
        {
            "metric": "brightness",
            "value": 20,
            "unit": "level",
            "value_kind": "measured",
            "input_mode": "live",
            "method": "center-luma-rec709-v1",
            "quality": "ok",
            "observed_at": (now + timedelta(seconds=n)).isoformat(),
        }
        for n in [0, 2]
    ]
    phone.post(room + "/telemetry/batch", json={"samples": samples})
    sensors.expire_stale(now.timestamp() + 18)
    sensors.expire_stale(now.timestamp() + 24)
    assert parent.get(room + "/alerts").json()["alerts"][0]["reason"] == "signal_lost"
    rows = parent.get(room + "/telemetry").json()["samples"]
    assert (
        len(rows) == 3 and rows[0]["quality"] == "missing" and rows[0]["value"] is None
    )
