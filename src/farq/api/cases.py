"""Case endpoints, matching the contract with Roshan's WhatsApp bot (FARQ backend
integration guide, section 2), plus a debug view for our own tools."""

import io
import json
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from farq.api.deps import EnqueueDep, MediaDep, RepoDep, SettingsDep, require_api_key
from farq.api.result import build_result, status_of
from farq.domain.casefile import CaseContext
from farq.intake import IntakeError, submit_media

router = APIRouter(prefix="/cases", tags=["cases"], dependencies=[Depends(require_api_key)])

ETA_SECONDS = 45  # measured: 39-46 s upload to verdict for a 1-minute video (24 Oct)


class TextClaim(BaseModel):
    media_type: Literal["text"]
    text: str
    idempotency_key: str | None = None
    user_ref: str | None = None
    caption: str | None = None
    is_forwarded: bool | None = None
    frequently_forwarded: bool | None = None
    language: str | None = None
    received_at: str | None = None


class Answers(BaseModel):
    claims_to_be: (
        Literal[
            "official", "famous_expert", "bank_upi", "family_friend", "company_boss", "not_sure"
        ]
        | None
    ) = None
    asks_for: Literal["invest", "send_money", "otp_link_kyc", "nothing_yet"] | None = None
    money_sent: bool | None = None


def _bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).lower() in {"true", "1", "yes"}


@router.post("", status_code=202)
async def create_case(
    request: Request, repo: RepoDep, media: MediaDep, enqueue: EnqueueDep, settings: SettingsDep
) -> dict[str, Any]:
    """Multipart form for video / audio / image, or JSON for a text claim.
    The same idempotency_key always maps to the same case."""
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            claim = TextClaim.model_validate(json.loads(await request.body()))
        except (ValueError, ValidationError) as exc:
            raise HTTPException(422, f"Invalid text claim: {exc}") from exc
        fields: dict[str, Any] = claim.model_dump()
        filename, fileobj, content_type = (
            "message.txt",
            io.BytesIO(claim.text.encode()),
            "text/plain",
        )
    else:
        form = await request.form()
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise HTTPException(422, "Send the media as a 'file' form field, or JSON for text")
        fields = dict(form)
        filename, fileobj = upload.filename or "", upload.file
        content_type = upload.content_type or "application/octet-stream"

    message_id = fields.get("idempotency_key") or fields.get("message_id") or uuid4().hex
    user_ref = fields.get("user_ref")
    context = CaseContext(
        caption=fields.get("caption") or None,
        is_forwarded=_bool(fields.get("is_forwarded")),
        frequently_forwarded=_bool(fields.get("frequently_forwarded")),
        language=fields.get("language") or None,
        received_at=fields.get("received_at") or None,
        money_sent=_bool(fields.get("money_sent")),
        claimed_person=fields.get("claimed_person") or None,
    )
    try:
        result = await run_in_threadpool(
            submit_media,
            repo=repo,
            media=media,
            enqueue=enqueue,
            channel="whatsapp" if user_ref else "upload",
            message_id=str(message_id)[:128],
            user_id=str(user_ref or "local-upload"),
            user_hash_key=settings.user_hash_key.get_secret_value(),
            filename=filename,
            fileobj=fileobj,
            content_type=content_type,
            context=context,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
        )
    except IntakeError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    case = repo.load(result.case_id)
    status = status_of(case)["status"] if case else "queued"
    return {"case_id": str(result.case_id), "status": status, "eta_seconds": ETA_SECONDS,
            "duplicate": result.duplicate}  # fmt: skip


@router.patch("/{case_id}/answers")
def record_answers(case_id: UUID, answers: Answers, repo: RepoDep) -> dict[str, str]:
    """Guided answers from the bot. They can arrive before or after the verdict;
    the result is built when read, so they always count."""
    case = repo.load(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    updates = answers.model_dump(exclude_none=True)
    repo.update_context(case_id, case.context.model_copy(update=updates))
    repo.commit()
    return {"status": "answers_recorded", "case_id": str(case_id)}


@router.get("/{case_id}/report.pdf")
def get_report(case_id: UUID, repo: RepoDep) -> Response:
    """Evidence PDF for the user to attach to a cybercrime.gov.in complaint."""
    from farq.report import report_pdf

    case = repo.load(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.decision is None:
        raise HTTPException(409, "The check isn't finished yet")
    return Response(
        report_pdf(case),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="farq-report-{case_id}.pdf"'},
    )


@router.get("/{case_id}")
def get_case(case_id: UUID, repo: RepoDep) -> JSONResponse:
    """Processing status, or the full result when done (the bot polls this)."""
    case = repo.load(case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return JSONResponse(build_result(case))


# --- Debug view for our own tools (farq check): stages, timings, evidence -------


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


@router.get("/{case_id}/debug")
def get_case_debug(case_id: UUID, repo: RepoDep) -> CaseView:
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
