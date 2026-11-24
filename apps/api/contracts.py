"""Response models shared by the HTTP API and the generated web client."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .sensors import Sample
from .vision import Item, Skill


class Session(BaseModel):
    session_id: str
    role: Literal["parent", "glasses"]


class Snapshot(Session):
    learner_id: str
    silent: bool
    seq: int


class Readiness(BaseModel):
    api: Literal["ready"]
    vision_configured: bool
    model: dict[str, Any]


class PhoneSetup(BaseModel):
    mode: Literal["lan", "public"] = "lan"
    public_unavailable: bool = False
    certificate: str | None
    fingerprint: str | None


class Invite(BaseModel):
    url: str
    code: str
    session_id: str


class JobId(BaseModel):
    job_id: str


class CaptureReceipt(JobId):
    capture_id: str
    tap_side: Literal["left", "right"] | None = None


class QuestionResult(Item):
    id: str
    revision: int
    verification: Literal["visual", "sympy", "conflict"]


class Job(BaseModel):
    id: str
    capture_id: str
    session_id: str
    status: Literal["queued", "running", "completed", "failed"]
    error: str | None
    result: list[QuestionResult] | None
    provider: str | None
    model: str | None
    request_id: str | None
    usage: dict[str, Any] | None
    latency: float | None
    created: float


class Event(BaseModel):
    event_id: str
    session_id: str
    seq: int
    type: Literal[
        "capture.received",
        "grading.queued",
        "grading.running",
        "grading.completed",
        "grading.failed",
        "session.privacy",
        "question.reviewed",
        "mistake.saved",
        "mastery.updated",
        "recommendations.ready",
        "telemetry.updated",
        "alert.raised",
        "alert.cleared",
    ]
    occurred_at: datetime
    payload: dict[str, Any]


class Review(BaseModel):
    revision: int = Field(ge=0)
    question: str = Field(min_length=1, max_length=2500)
    student_answer: str = Field(min_length=1, max_length=500)


class PracticeAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=100)
    idem: str = Field(min_length=8, max_length=100)


class SkillPrediction(BaseModel):
    skill: Skill
    probability: float | None
    evidence_count: int


class Mastery(BaseModel):
    available: bool
    device: str
    model_version: str | None
    skills: list[SkillPrediction]


class Exercise(BaseModel):
    id: str
    skill: Skill
    question: str


class Exercises(BaseModel):
    items: list[Exercise]


class PracticeResult(BaseModel):
    correct: bool
    question: str
    reference_answer: str
    explanation: str


class Mistake(QuestionResult):
    capture_id: str
    created: float


class Mistakes(BaseModel):
    items: list[Mistake]


class Alert(Sample):
    id: str
    started_at: datetime
    ended_at: datetime | None
    reason: str | None


class Alerts(BaseModel):
    alerts: list[Alert]


class Samples(BaseModel):
    samples: list[Sample]


class Received(BaseModel):
    accepted: int
    active_alerts: list[Alert]


class Hotspot(BaseModel):
    id: str
    label: str
    description: str
    position: tuple[float, float, float]


class Product(BaseModel):
    sku: str
    name: str
    description: str
    price_cny: int
    weight_g: int | None
    image_url: str
    model_url: str
    hotspots: list[Hotspot]


class Catalog(BaseModel):
    products: list[Product]
    subscription_cny: int
    assistant_path: str
