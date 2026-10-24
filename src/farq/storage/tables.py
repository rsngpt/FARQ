"""Database tables. Change them only through an Alembic migration."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB on Postgres, plain JSON elsewhere (tests use SQLite).
JsonType = JSON().with_variant(JSONB(), "postgresql")


class UTCDateTime(TypeDecorator):
    """Always returns timezone-aware UTC datetimes, even from SQLite, which drops
    the timezone."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Base(DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JsonType,
        list[str]: JsonType,
        datetime: UTCDateTime(),
    }


class CaseRow(Base):
    __tablename__ = "cases"
    # Dedupe: one case per channel message, however often the webhook retries.
    __table_args__ = (UniqueConstraint("channel", "message_id", name="uq_cases_channel_message"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(32))
    message_id: Mapped[str] = mapped_column(String(128))
    user_hash: Mapped[str] = mapped_column(String(64))
    media_key: Mapped[str] = mapped_column(String(255))
    media_sha256: Mapped[str] = mapped_column(String(64), index=True)
    media_bytes: Mapped[int] = mapped_column(BigInteger)
    context: Mapped[dict[str, Any]]
    status: Mapped[str] = mapped_column(String(16))
    decision: Mapped[dict[str, Any] | None]
    reply_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]


class EvidenceRow(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    type: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(16))
    strength: Mapped[str] = mapped_column(String(16))
    indicates: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(8))
    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]]
    created_at: Mapped[datetime]


class ArtifactRow(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    kind: Mapped[str] = mapped_column(String(32))
    storage_key: Mapped[str | None] = mapped_column(String(255))
    data: Mapped[dict[str, Any]]
    model_name: Mapped[str | None] = mapped_column(String(128))
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime]


class StageRunRow(Base):
    """One row per (case, stage): its latest run, used for timings and to skip
    stages that already ran when a case is retried."""

    __tablename__ = "stage_runs"

    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    stage: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime]
    error: Mapped[str | None] = mapped_column(Text)


class AuditRow(Base):
    """Every verdict and reviewer action: who, when, evidence IDs, model versions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    at: Mapped[datetime]
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    case_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cases.id"), index=True)
    verdict: Mapped[str | None] = mapped_column(String(32))
    evidence_ids: Mapped[list[str]]
    model_versions: Mapped[list[str]]
    details: Mapped[dict[str, Any]]


class LibraryClipRow(Base):
    """A genuine recording of a person, for the source map. Who it shows, where it
    came from and the consent note are kept with it."""

    __tablename__ = "library_clips"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    person: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)  # e.g. "team recording, 24 Oct" or a URL
    consent_note: Mapped[str | None] = mapped_column(Text)
    media_key: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    duration_s: Mapped[float]
    fingerprints: Mapped[dict[str, Any]]  # {"fps", "frames": [{"t", "pdq", "q"}]}
    transcript: Mapped[dict[str, Any] | None]  # same shape as the transcript artifact
    created_at: Mapped[datetime]


class KnownFakeRow(Base):
    """Files a person has confirmed as scams (reviewer or a public fact-check)."""

    __tablename__ = "known_fakes"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    label: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    confirmed_by: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[datetime]
