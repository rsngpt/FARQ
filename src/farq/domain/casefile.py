"""The CaseFile: everything FARQ knows about one check, and the Evidence behind it."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_evidence_id() -> str:
    return f"ev_{uuid4().hex[:12]}"


class SourceType(StrEnum):
    """Where a piece of evidence comes from."""

    MODEL = "model"  # an ML model's output
    MATCH = "match"  # a match against our library: hashes, source clips, scam scripts
    LIST = "list"  # an official list: RBI, NSE, SEBI
    RULE = "rule"  # a deterministic check


class Strength(StrEnum):
    WEAK = "weak"
    STRONG = "strong"
    DECISIVE = "decisive"

    @property
    def rank(self) -> int:
        return {"weak": 1, "strong": 2, "decisive": 3}[self.value]


class Indicates(StrEnum):
    """Which way a piece of evidence points. Internal only: users never see
    'not_scam', and FARQ never calls a video genuine."""

    SCAM = "scam"
    NOT_SCAM = "not_scam"
    UNCLEAR = "unclear"


class Level(StrEnum):
    """What users see instead of a raw score."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Evidence(BaseModel):
    id: str = Field(default_factory=new_evidence_id)
    stage: str
    type: str  # e.g. "known_fake_hash", "av_binding"
    source_type: SourceType
    strength: Strength
    indicates: Indicates
    reason: str  # one plain sentence a user can read
    level: Level | None = None
    human_reviewed: bool = False  # a person confirmed this (needed for CONFIRMED)
    model_name: str | None = None
    model_version: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)  # raw scores; never shown to users
    created_at: datetime = Field(default_factory=utcnow)


class StageStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    STUB = "stub"  # placeholder stage that does nothing yet


class StageTiming(BaseModel):
    stage: str
    status: StageStatus
    started_at: datetime
    ended_at: datetime
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        return (self.ended_at - self.started_at).total_seconds() * 1000


class Verdict(StrEnum):
    CONFIRMED_SCAM = "confirmed_scam"
    LIKELY_SCAM = "likely_scam"
    NOT_VERIFIED = "not_verified"

    @property
    def label(self) -> str:
        return self.value.replace("_", " ").upper()


class Decision(BaseModel):
    verdict: Verdict
    rule_id: str
    evidence_ids: list[str]  # every verdict cites the evidence behind it
    needs_review: bool
    rules_version: str
    decided_at: datetime = Field(default_factory=utcnow)


class CaseStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    DECIDED = "decided"
    FAILED = "failed"


class CaseContext(BaseModel):
    """Answers from the guided conversation (fixed buttons)."""

    claimed_person: str | None = None
    claimed_ask: str | None = None
    money_sent: bool | None = None


class CaseFile(BaseModel):
    id: UUID
    channel: str
    message_id: str
    user_hash: str
    media_key: str
    media_sha256: str
    media_bytes: int
    context: CaseContext
    status: CaseStatus
    created_at: datetime
    evidence: list[Evidence] = Field(default_factory=list)
    timings: list[StageTiming] = Field(default_factory=list)
    decision: Decision | None = None
    reply_text: str | None = None

    def evidence_by_ids(self, ids: list[str]) -> list[Evidence]:
        by_id = {e.id: e for e in self.evidence}
        return [by_id[i] for i in ids if i in by_id]
