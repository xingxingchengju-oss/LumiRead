"""Reading-monitor decisions on the source-video clock. One tick is 1/504 point."""

from collections import Counter
from typing import Literal

from typing_extensions import TypedDict

Activity = Literal["reading", "video", "rest", "unknown"]
Medium = Literal[
    "phone", "computer", "tablet", "screen", "paper", "other_text", "unknown", "none"
]
Kind = Literal["paper", "digital"]
PATCH_SECONDS = 7
TICKS = 504
RULE = "ritw-monitor-v1"
# Per effective second. Every six active seconds post their combined ticks.
READ_RATE = {
    "phone": 28,
    "computer": 24,
    "paper": 21,
    "other_text": 21,
    "tablet": 21,
}
MAX_SCORE = 100 * TICKS


class FrameTarget(TypedDict):
    second: float
    gaze: tuple[float, float] | None
    medium: Medium
    box: tuple[float, float, float, float] | None
    hit: bool


class Observation(TypedDict):
    activity: Activity
    medium: Medium
    summary: str
    frames: list[FrameTarget]


class Patch(TypedDict):
    start: int
    end: int
    read_votes: int
    nonread_votes: int
    missing: list[int]
    reasons: list[str]
    review: Observation | None
    evidence_start: int | None
    activity: Activity
    medium: Medium


class MonitorClip(TypedDict):
    id: str
    kind: Kind
    start: int
    end: int
    patches: list[Patch]
    # Snapshot at start + index: cumulative reading seconds, video seconds, score ticks.
    points: list[tuple[int, int, int]]
    reminders: list[int]


class Monitor(TypedDict):
    rule_version: str
    ticks_per_point: int
    clips: list[MonitorClip]


def vote_patches(start: int, end: int, votes: dict[int, int]) -> list[Patch]:
    patches = []
    previous, last_review = None, None
    for grid in range(start - start % PATCH_SECONDS, end, PATCH_SECONDS):
        a, b = max(grid, start), min(grid + PATCH_SECONDS, end)
        counted = Counter(votes[t] for t in range(a, b) if t in votes)
        yes, no = counted[1], counted[0]
        missing = [t for t in range(a, b) if t not in votes]
        choice = None if yes == no else int(yes > no)
        reasons = []
        if yes + no:
            if previous is None:
                reasons.append("first" if last_review is None else "resume")
            elif choice is not None and choice != previous:
                reasons.append("enter_reading" if choice else "switch")
            if yes == no:
                reasons.append("tie")
            elif abs(yes - no) == 1:
                reasons.append("close_vote")
            if missing:
                reasons.append("gap")
            if not reasons and last_review is not None and grid - last_review >= 28:
                reasons.append("periodic")
        if reasons:
            last_review = grid
        patches.append(
            Patch(
                start=a,
                end=b,
                read_votes=yes,
                nonread_votes=no,
                missing=missing,
                reasons=reasons,
                review=None,
                evidence_start=None,
                activity="unknown",
                medium="unknown",
            )
        )
        previous = None if missing or not (yes + no) else choice
    return patches


def decide(patch: Patch, observation: Observation | None) -> tuple[Activity, Medium]:
    margin = patch["read_votes"] - patch["nonread_votes"]
    if observation:
        visual = observation["activity"]
        medium = observation["medium"]
        if medium == "screen":
            medium = "unknown"
        if visual == "video":
            return "video", medium
        if visual == "rest" and margin <= 1:
            return "rest", "none"
        if visual == "reading" and margin >= -1:
            return "reading", medium
        if visual != "unknown":
            return "unknown", "unknown"
    return ("reading", "unknown") if margin > 1 else ("unknown", "unknown")


def fuse(patches, get_observation):
    evidence, evidence_start, last_decision = None, None, "unknown"
    for p in patches:
        if p["missing"]:
            evidence, evidence_start = None, None
        if not (p["read_votes"] + p["nonread_votes"]):
            last_decision = "unknown"
            continue
        if not p["reasons"] and (evidence is None or last_decision == "unknown"):
            p["reasons"].append("unresolved")
        if p["reasons"]:
            evidence = get_observation(p)
            evidence_start = p["start"] if evidence else None
            p["review"] = evidence
        p["evidence_start"] = evidence_start
        p["activity"], p["medium"] = decide(p, evidence)
        last_decision = p["activity"]
        if evidence and evidence["activity"] == "unknown":
            evidence = None
    return patches


def score(seconds, start=0):
    total = reading = video = rest = pending = pending_ticks = 0
    points = [(0, 0, 0)]
    reminders = []
    for boundary, (activity, medium) in enumerate(seconds, start + 1):
        reading += activity == "reading"
        video += activity == "video"
        rate = READ_RATE.get(medium, 0) if activity == "reading" else 0
        if activity == "video":
            rate = 28
        before = total
        if rate and total < MAX_SCORE:
            pending += 1
            pending_ticks += rate
            if pending == 6:
                total = min(MAX_SCORE, total + pending_ticks)
                pending = pending_ticks = 0
        if activity == "rest":
            rest += 1
            if rest > 10:
                total = max(0, total - 144)
        else:
            rest = 0
        if before < MAX_SCORE and total == MAX_SCORE:
            reminders.append(boundary)
        points.append((reading, video, total))
    return points, reminders


def timeline(patches):
    for p in patches:
        for t in range(p["start"], p["end"]):
            yield (
                ("unknown", "unknown")
                if t in p["missing"]
                else (p["activity"], p["medium"])
            )
