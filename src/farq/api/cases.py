from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel

from farq.api.deps import EnqueueDep, MediaDep, RepoDep, SettingsDep, require_api_key
from farq.domain.casefile import CaseContext
from farq.intake import IntakeError, submit_media

router = APIRouter(prefix="/cases", tags=["cases"], dependencies=[Depends(require_api_key)])


class CaseCreated(BaseModel):
    case_id: UUID
    duplicate: bool


class EvidenceView(BaseModel):
    """Evidence without raw details: reasons and levels only, never scores."""

    id: str
    type: str
    source_type: str
    strength: str
    indicates: str
    level: str | None
    reason: str


class StageView(BaseModel):
    stage: str
    status: str
    duration_ms: int
    error: str | None


class ArtifactView(BaseModel):
    """What a stage produced; the data itself is left out (it can be large)."""

    kind: str
    stage: str
    storage_key: str | None
    model_name: str | None
    model_version: str | None


class CaseView(BaseModel):
    id: UUID
    status: str
    verdict: str | None
    needs_review: bool
    reply_text: str | None
    evidence: list[EvidenceView]
    artifacts: list[ArtifactView]
    stages: list[StageView]


@router.post("", status_code=202)
def create_case(
    file: UploadFile,
    repo: RepoDep,
    media: MediaDep,
    enqueue: EnqueueDep,
    settings: SettingsDep,
    message_id: Annotated[str | None, Form(max_length=128)] = None,
    money_sent: Annotated[bool | None, Form()] = None,
    claimed_person: Annotated[str | None, Form(max_length=200)] = None,
    claimed_ask: Annotated[str | None, Form(max_length=200)] = None,
) -> CaseCreated:
    """Local upload intake. Pass message_id to make retries safe (same ID, same case)."""
    try:
        result = submit_media(
            repo=repo,
            media=media,
            enqueue=enqueue,
            channel="upload",
            message_id=message_id or uuid4().hex,
            user_id="local-upload",
            user_hash_key=settings.user_hash_key.get_secret_value(),
            filename=file.filename or "",
            fileobj=file.file,
            content_type=file.content_type or "application/octet-stream",
            context=CaseContext(
                claimed_person=claimed_person, claimed_ask=claimed_ask, money_sent=money_sent
            ),
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )
    except IntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return CaseCreated(case_id=result.case_id, duplicate=result.duplicate)


@router.get("/{case_id}")
def get_case(case_id: UUID, repo: RepoDep) -> CaseView:
    case = repo.load(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return CaseView(
        id=case.id,
        status=case.status,
        verdict=case.decision.verdict.label if case.decision else None,
        needs_review=case.decision.needs_review if case.decision else False,
        reply_text=case.reply_text,
        evidence=[EvidenceView.model_validate(e, from_attributes=True) for e in case.evidence],
        artifacts=[ArtifactView.model_validate(a, from_attributes=True) for a in case.artifacts],
        stages=[
            StageView(
                stage=t.stage, status=t.status, duration_ms=round(t.duration_ms), error=t.error
            )
            for t in case.timings
        ],
    )
