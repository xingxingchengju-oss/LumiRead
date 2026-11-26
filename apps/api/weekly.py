"""One demonstration week assembled from the reading monitor's frozen predictions."""

import json
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from . import storage
from .monitor import timeline

RITW = storage.ROOT / "artifacts/ritw"
MONDAY = date(2026, 11, 16)
PROMPT_VERSION = "parent-weekly.zh.v2"
PROMPT_PATH = Path(__file__).with_name("prompts") / (PROMPT_VERSION + ".txt")
PROMPT_SHA256 = "e987b3727bcfc08179750eef4014ec118231986f7917c754e9226300d66d2c30"
PUBLICATION = RITW / (PROMPT_VERSION + ".json")
SOURCE_NOTE = (
    "本周报采用 Meta Reading in the Wild 成人实拍片段的模型识别结果。"
    "学生和七天日程为演示编排，时长沿用原片段。"
)


class ActivitySeconds(BaseModel):
    total: int
    reading: int
    video: int
    rest: int
    unknown: int


class WeeklyDay(BaseModel):
    date: date
    totals: ActivitySeconds


class WeekRange(BaseModel):
    start: date
    end: date


class WeeklyFact(BaseModel):
    id: str
    text: str


class WeeklyInput(BaseModel):
    student_label: str
    week: WeekRange
    source_note: str
    totals: ActivitySeconds
    days: list[WeeklyDay]
    reading_by_medium: dict[str, int]
    facts: list[WeeklyFact]

    def prompt_input(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class WeeklyClip(BaseModel):
    id: str
    date: date
    start: int
    end: int


class WeeklySuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_id: str
    action: str = Field(
        description=(
            "一句可实行的用眼建议。描述读完一页或一段视频结束等自然节点，"
            "以及抬头看看远处、放下屏幕活动一下等具体的用眼间歇动作。"
            "建议只写动作，观察数据由页面另行展示，不添加时长、距离或次数目标。"
        )
    )


class WeeklyNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(
        description=(
            "温和简洁的一段家校观察，在开头交代片段范围。所用时长原样照录对应 facts 中的数值和单位，"
            "不添加差值、倍数、百分比或约数。"
        )
    )
    summary_fact_ids: list[str] = Field(
        description="逐一列出摘要中每个观察及每个数值对应的输入事实 ID。"
    )
    suggestions: list[WeeklySuggestion] = Field(
        description=(
            "两条互补的用眼习惯建议。第一条用阅读事实引出阅读间歇，"
            "第二条用手机阅读或观看视频的事实引出离屏休息。"
            "各自给出不同的具体做法，动作与 fact_id 对应。"
        )
    )


class WeeklyPublication(BaseModel):
    provider: str
    model: str
    request_sha256: str
    prompt_version: str
    prompt_sha256: str
    schema_sha256: str
    input_sha256: str
    narrative: WeeklyNarrative


class WeeklyReport(WeeklyInput):
    clips: list[WeeklyClip]
    publication: WeeklyPublication | None


def display_time(seconds: int) -> str:
    minutes, remainder = divmod(seconds, 60)
    if not minutes:
        return f"{remainder}秒"
    return f"{minutes}分{remainder}秒" if remainder else f"{minutes}分"


def activity_totals(counts: Counter) -> ActivitySeconds:
    activities = Counter()
    for (activity, _), seconds in counts.items():
        activities[activity] += seconds
    return ActivitySeconds(
        total=counts.total(),
        **{key: activities[key] for key in ("reading", "video", "rest", "unknown")},
    )


def week_facts(totals, media, days):
    facts = [
        WeeklyFact(
            id="recorded", text=f"本周片段共记录了{display_time(totals.total)}。"
        ),
        WeeklyFact(
            id="reading", text=f"本周片段里，孩子阅读了{display_time(totals.reading)}。"
        ),
        WeeklyFact(
            id="video", text=f"记录中观看视频的时间合计{display_time(totals.video)}。"
        ),
        WeeklyFact(
            id="rest",
            text=f"记录中暂时离开阅读或视频的时间合计{display_time(totals.rest)}。",
        ),
        WeeklyFact(
            id="unknown", text=f"还有{display_time(totals.unknown)}的片段无法判断活动。"
        ),
    ]
    for key, label in (
        ("paper", "纸质阅读"),
        ("phone", "手机文字阅读"),
        ("computer", "电脑文字阅读"),
        ("other_text", "其他文字阅读"),
    ):
        facts.append(
            WeeklyFact(
                id=key, text=f"本周记录到的{label}合计{display_time(media[key])}。"
            )
        )
    facts.append(
        WeeklyFact(
            id="unknown_medium",
            text=f"有{display_time(media['unknown'])}已识别为阅读，载体待定。",
        )
    )
    for day in days:
        weekday = "周" + "一二三四五六日"[day.date.weekday()]
        t = day.totals
        facts.append(
            WeeklyFact(
                id=day.date.isoformat(),
                text=(
                    f"{weekday}的片段中，阅读{display_time(t.reading)}，看视频{display_time(t.video)}，"
                    f"暂停{display_time(t.rest)}，活动待定{display_time(t.unknown)}。"
                ),
            )
        )
    return facts


def assemble_week(root: Path = RITW) -> tuple[WeeklyInput, list[WeeklyClip]]:
    # Both sources describe half-open intervals on the original video clock.
    recordings = {}
    for clip in json.loads((root / "monitor.json").read_text())["clips"]:
        recordings[clip["id"]] = (
            clip["start"],
            clip["end"],
            Counter(timeline(clip["patches"])),
        )
    tests = json.loads((root / "monitor-metrics.json").read_text())["test_recordings"]
    for clip in tests:
        runs = clip["predictions"]
        counts = Counter()
        for start, end, activity, medium in runs:
            counts[activity, medium] += end - start
        if clip["id"] in recordings:
            raise ValueError("Duplicate weekly recording")
        recordings[clip["id"]] = (runs[0][0], runs[-1][1], counts)

    daily = [Counter() for _ in range(7)]
    sources = []
    for index, (clip_id, (start, end, counts)) in enumerate(sorted(recordings.items())):
        if counts.total() != end - start:
            raise ValueError(f"Incomplete source timeline for {clip_id}")
        weekday = index % 7
        daily[weekday].update(counts)
        sources.append(
            WeeklyClip(
                id=clip_id, date=MONDAY + timedelta(days=weekday), start=start, end=end
            )
        )
    days = [
        WeeklyDay(date=MONDAY + timedelta(days=i), totals=activity_totals(counts))
        for i, counts in enumerate(daily)
    ]
    all_counts = sum(daily, Counter())
    totals = activity_totals(all_counts)
    media = Counter(
        {
            m: seconds
            for (activity, m), seconds in all_counts.items()
            if activity == "reading"
        }
    )
    return WeeklyInput(
        student_label="小禾",
        week=WeekRange(start=days[0].date, end=days[-1].date),
        source_note=SOURCE_NOTE,
        totals=totals,
        days=days,
        reading_by_medium=dict(media),
        facts=week_facts(totals, media, days),
    ), sources


# Match whole quantities, so an invented duration cannot borrow digits from two facts.
_AMOUNT = re.compile(
    r"(?:\d+(?:\.\d+)?(?:小时|分钟|分|秒钟|秒))+|\d+(?:\.\d+)?(?:[%％次天倍]|厘米)?"
    r"|[零〇一二两三四五六七八九十百千半]+(?:小时|分钟|秒钟|秒|厘米|倍|成)"
)


def check_narrative(narrative: WeeklyNarrative, facts: list[WeeklyFact]):
    indexed = {f.id: f.text for f in facts}

    def check_text(text, ids):
        if not text.strip() or not ids or not set(ids) <= indexed.keys():
            raise ValueError("Missing text or unrecognized weekly fact ID")
        cited = " ".join(indexed[i] for i in ids)

        def amounts(value):
            compact = re.sub(r"\s+", "", value)
            return {
                q.replace("分钟", "分").replace("秒钟", "秒")
                for q in _AMOUNT.findall(compact)
            }

        unsupported = amounts(text) - amounts(cited)
        if unsupported:
            raise ValueError(
                "引用事实中没有这些数值：" + "、".join(sorted(unsupported))
            )

    if len(narrative.suggestions) != 2:
        raise ValueError("The weekly report needs two suggestions")
    if (
        not 65 <= len(narrative.summary.strip()) <= 145
        or "\n" in narrative.summary.strip()
    ):
        raise ValueError("Expected one short weekly summary paragraph")
    check_text(narrative.summary, narrative.summary_fact_ids)
    for suggestion in narrative.suggestions:
        check_text(suggestion.action, [suggestion.fact_id])


def schema_digest():
    return storage.digest(
        json.dumps(WeeklyNarrative.model_json_schema(), sort_keys=True)
    )


def read_publication(input_sha256: str, facts: list[WeeklyFact], path: Path):
    try:
        published = WeeklyPublication.model_validate_json(path.read_bytes())
        if (
            published.prompt_version != PROMPT_VERSION
            or published.prompt_sha256 != PROMPT_SHA256
            or published.input_sha256 != input_sha256
            or published.schema_sha256 != schema_digest()
        ):
            return None
        check_narrative(published.narrative, facts)
        return published
    except (FileNotFoundError, ValueError):
        return None


def weekly_report() -> WeeklyReport:
    data, clips = assemble_week()
    published = read_publication(
        storage.digest(data.prompt_input()), data.facts, PUBLICATION
    )
    return WeeklyReport(**data.model_dump(), clips=clips, publication=published)
