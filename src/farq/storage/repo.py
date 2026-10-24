from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from farq.domain.casefile import (
    Artifact,
    CaseContext,
    CaseFile,
    CaseStatus,
    Decision,
    Evidence,
    StageTiming,
    utcnow,
)
from farq.storage.tables import (
    ArtifactRow,
    AuditRow,
    CaseRow,
    EvidenceRow,
    KnownFakeRow,
    StageRunRow,
)


def media_key_for(case_id: UUID, extension: str) -> str:
    return f"cases/{case_id}/original{extension}"


class CaseRepository:
    """Reads and writes CaseFiles. Only create_case commits; otherwise the caller decides."""

    def __init__(self, session: Session):
        self.session = session

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

    def find_by_message(self, channel: str, message_id: str) -> UUID | None:
        return self.session.scalar(
            select(CaseRow.id).where(CaseRow.channel == channel, CaseRow.message_id == message_id)
        )

    def create_case(
        self,
        *,
        channel: str,
        message_id: str,
        user_hash: str,
        media_sha256: str,
        media_bytes: int,
        media_extension: str,
        context: CaseContext,
    ) -> tuple[UUID, bool]:
        """Create a case and commit. Returns (case_id, duplicate); a message already
        seen on this channel returns the existing case instead."""
        existing = self.find_by_message(channel, message_id)
        if existing is not None:
            return existing, True
        case_id = uuid4()
        self.session.add(
            CaseRow(
                id=case_id,
                channel=channel,
                message_id=message_id,
                user_hash=user_hash,
                media_key=media_key_for(case_id, media_extension),
                media_sha256=media_sha256,
                media_bytes=media_bytes,
                context=context.model_dump(mode="json"),
                status=CaseStatus.RECEIVED,
                decision=None,
                reply_text=None,
                created_at=utcnow(),
            )
        )
        try:
            self.session.commit()
        except IntegrityError:
            # Another request created it between our check and insert.
            self.session.rollback()
            existing = self.find_by_message(channel, message_id)
            if existing is None:
                raise
            return existing, True
        return case_id, False

    def load(self, case_id: UUID) -> CaseFile | None:
        row = self.session.get(CaseRow, case_id)
        if row is None:
            return None
        evidence = self.session.scalars(
            select(EvidenceRow)
            .where(EvidenceRow.case_id == case_id)
            .order_by(EvidenceRow.created_at, EvidenceRow.id)
        )
        artifacts = self.session.scalars(
            select(ArtifactRow)
            .where(ArtifactRow.case_id == case_id)
            .order_by(ArtifactRow.created_at, ArtifactRow.id)
        )
        runs = self.session.scalars(
            select(StageRunRow)
            .where(StageRunRow.case_id == case_id)
            .order_by(StageRunRow.started_at)
        )
        return CaseFile(
            id=row.id,
            channel=row.channel,
            message_id=row.message_id,
            user_hash=row.user_hash,
            media_key=row.media_key,
            media_sha256=row.media_sha256,
            media_bytes=row.media_bytes,
            context=CaseContext.model_validate(row.context),
            status=CaseStatus(row.status),
            created_at=row.created_at,
            evidence=[Evidence.model_validate(e, from_attributes=True) for e in evidence],
            artifacts=[Artifact.model_validate(a, from_attributes=True) for a in artifacts],
            timings=[StageTiming.model_validate(r, from_attributes=True) for r in runs],
            decision=Decision.model_validate(row.decision) if row.decision else None,
            reply_text=row.reply_text,
        )

    def set_status(self, case_id: UUID, status: CaseStatus) -> None:
        self.session.get_one(CaseRow, case_id).status = status

    def stages_run(self, case_id: UUID) -> set[str]:
        """Stages with a recorded run (ok, stub or failed). A retry skips them;
        a stage interrupted mid-run has no record, so it runs again."""
        return set(
            self.session.scalars(select(StageRunRow.stage).where(StageRunRow.case_id == case_id))
        )

    def replace_stage_outputs(
        self, case_id: UUID, stage: str, evidence: list[Evidence], artifacts: list[Artifact]
    ) -> None:
        """Swap a stage's evidence and artifacts, so running a stage twice never
        duplicates rows."""
        for table in (EvidenceRow, ArtifactRow):
            self.session.execute(
                delete(table).where(table.case_id == case_id, table.stage == stage)
            )
        for e in evidence:
            self.session.add(EvidenceRow(case_id=case_id, **e.model_dump()))
        for a in artifacts:
            self.session.add(ArtifactRow(case_id=case_id, **a.model_dump()))

    def record_stage(self, case_id: UUID, timing: StageTiming) -> None:
        self.session.merge(StageRunRow(case_id=case_id, **timing.model_dump()))

    def save_decision(self, case_id: UUID, decision: Decision, reply_text: str) -> None:
        row = self.session.get_one(CaseRow, case_id)
        row.decision = decision.model_dump(mode="json")
        row.reply_text = reply_text
        row.status = CaseStatus.DECIDED

    def add_audit(
        self,
        *,
        actor: str,
        action: str,
        case_id: UUID | None,
        verdict: str | None = None,
        evidence_ids: list[str] | None = None,
        model_versions: list[str] | None = None,
        details: dict | None = None,
    ) -> None:
        self.session.add(
            AuditRow(
                at=utcnow(),
                actor=actor,
                action=action,
                case_id=case_id,
                verdict=verdict,
                evidence_ids=evidence_ids or [],
                model_versions=model_versions or [],
                details=details or {},
            )
        )

    def list_audit(self, case_id: UUID) -> list[AuditRow]:
        return list(
            self.session.scalars(
                select(AuditRow).where(AuditRow.case_id == case_id).order_by(AuditRow.id)
            )
        )

    def find_known_fake(self, sha256: str) -> KnownFakeRow | None:
        return self.session.get(KnownFakeRow, sha256)

    def add_known_fake(
        self, *, sha256: str, label: str, confirmed_by: str, source_url: str | None = None
    ) -> None:
        self.session.merge(
            KnownFakeRow(
                sha256=sha256,
                label=label,
                source_url=source_url,
                confirmed_by=confirmed_by,
                confirmed_at=utcnow(),
            )
        )

    def recent_decided(self, limit: int) -> list[CaseFile]:
        ids = self.session.scalars(
            select(CaseRow.id)
            .where(CaseRow.status == CaseStatus.DECIDED)
            .order_by(CaseRow.created_at.desc())
            .limit(limit)
        )
        return [case for case_id in ids if (case := self.load(case_id)) is not None]
