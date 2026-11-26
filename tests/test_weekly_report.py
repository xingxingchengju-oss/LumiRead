import json
from collections import Counter
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from apps.api import storage, vision, weekly
from apps.api.main import app
from scripts.weekly_report import publish


def test_weekly_seconds_trace_back_to_fifteen_distinct_source_intervals():
    data, sources = weekly.assemble_week()
    panel = json.loads((weekly.RITW / "monitor-metrics.json").read_text())
    classroom = json.loads((weekly.RITW / "monitor.json").read_text())
    raw = {}
    for c in panel["test_recordings"]:
        runs = c["predictions"]
        raw[c["id"]] = (
            runs[0][0],
            runs[-1][1],
            [(a, m) for start, end, a, m in runs for _ in range(end - start)],
        )
    for c in classroom["clips"]:
        decisions = [
            ("unknown", "unknown")
            if t in p["missing"]
            else (p["activity"], p["medium"])
            for p in c["patches"]
            for t in range(p["start"], p["end"])
        ]
        raw[c["id"]] = c["start"], c["end"], decisions

    assert len(raw) == len(sources) == 15
    assert [c.id for c in sources] == sorted(raw)
    daily = [Counter() for _ in range(7)]
    media = Counter()
    for index, c in enumerate(sources):
        start, end, states = raw[c.id]
        assert (c.start, c.end) == (start, end)
        assert len(states) == c.end - c.start
        assert c.date == weekly.MONDAY + timedelta(days=index % 7)
        daily[index % 7].update(a for a, m in states)
        media.update(m for a, m in states if a == "reading")
    for day, counts in zip(data.days, daily, strict=True):
        assert day.totals.total == counts.total()
        assert Counter(day.totals.model_dump(exclude={"total"})) == counts
    assert data.totals.model_dump() == {
        "total": 2984,
        "reading": 1111,
        "video": 1051,
        "rest": 294,
        "unknown": 528,
    }
    assert (
        data.reading_by_medium
        == media
        == {
            "paper": 444,
            "phone": 375,
            "computer": 171,
            "other_text": 88,
            "unknown": 33,
        }
    )


def test_published_report_is_anonymous_and_reads_without_provider(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    monkeypatch.setattr(
        vision, "config", lambda: pytest.fail("Public reads must stay offline")
    )
    with TestClient(app) as client:
        path = "/api/v1/eye-care/weekly-report"
        response = client.get(path)
        assert response.status_code == 200
        report = weekly.WeeklyReport.model_validate(response.json())
        assert report.student_label == "小禾" and len(report.days) == 7
        publication = report.publication
        assert publication is not None and publication.model and publication.provider
        assert publication.prompt_sha256 == storage.digest(
            weekly.PROMPT_PATH.read_text()
        )
        assert publication.input_sha256 == storage.digest(
            weekly.assemble_week()[0].prompt_input()
        )
        assert len(publication.request_sha256) == 64
        assert client.get(path).json() == response.json()
        monkeypatch.setattr(weekly, "PUBLICATION", tmp_path / "missing.json")
        partial = client.get(path).json()
        assert (
            partial["totals"] == report.totals.model_dump()
            and partial["publication"] is None
        )


def test_rejects_stale_facts_and_invented_quantities(tmp_path):
    data, _ = weekly.assemble_week()
    published = weekly.WeeklyPublication.model_validate_json(
        weekly.PUBLICATION.read_bytes()
    )
    path = tmp_path / "old.json"
    changed = published.model_copy(update={"input_sha256": "old"})
    path.write_text(changed.model_dump_json())
    assert (
        weekly.read_publication(storage.digest(data.prompt_input()), data.facts, path)
        is None
    )
    for fact, action in [
        ("imaginary", "一起读完这一页再歇一歇。"),
        ("reading", "读完要休息20分钟。"),
        ("reading", "每次都要读满十分钟。"),
        ("reading", "累计阅读了18分30秒。"),
    ]:
        invalid = published.narrative.model_copy(deep=True)
        invalid.suggestions[0] = weekly.WeeklySuggestion(fact_id=fact, action=action)
        with pytest.raises(ValueError):
            weekly.check_narrative(invalid, data.facts)


def test_publisher_sends_frozen_prompt_and_aggregate_separately_then_reuses_result(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LUMIREAD_VAR", str(tmp_path))
    expected = weekly.WeeklyPublication.model_validate_json(
        weekly.PUBLICATION.read_bytes()
    ).narrative
    posted = []

    def transport(request):
        body = json.loads(request.content)
        posted.append(body)
        assert body["instructions"] == weekly.PROMPT_PATH.read_text()
        assert body["store"] is False
        content = json.loads(body["input"][0]["content"])
        assert content == weekly.assemble_week()[0].model_dump(mode="json")
        assert "clips" not in content
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "model": "test-text",
                "id": "test-receipt",
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": expected.model_dump_json()}
                        ]
                    }
                ],
            },
        )

    monkeypatch.setattr(
        vision,
        "config",
        lambda: [("OpenAI", "https://provider.test", "test-text", "test")],
    )
    path = tmp_path / "publication.json"
    first = publish(path, httpx.MockTransport(transport))
    assert publish(path, httpx.MockTransport(transport)) == first
    saved_draft = tmp_path / "weekly-report" / (first.request_sha256 + ".json")
    assert publish(tmp_path / "reviewed.json", draft=saved_draft) == first
    assert len(posted) == 1
