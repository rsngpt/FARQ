"""The police-report PDF. Opens from a link in WhatsApp: the link carries a
signature (HMAC of the case ID with our API key), so it works without the API
key header, only for that one case, and can't be guessed or edited to open
another case. The API key header also works (for the bot or our tools)."""

import hashlib
import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from farq.api.deps import RepoDep, SettingsDep
from farq.settings import get_settings

router = APIRouter(prefix="/cases", tags=["reports"])


def report_token(case_id: UUID | str) -> str:
    key = get_settings().intake_api_key.get_secret_value().encode()
    return hmac.new(key, f"report:{case_id}".encode(), hashlib.sha256).hexdigest()[:32]


def report_url(case_id: UUID | str) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/cases/{case_id}/report.pdf?t={report_token(case_id)}"


@router.get("/{case_id}/report.pdf")
def get_report(
    case_id: UUID,
    repo: RepoDep,
    settings: SettingsDep,
    t: Annotated[str | None, Query(max_length=64)] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Response:
    """Evidence PDF for the user to attach to a cybercrime.gov.in complaint."""
    expected_key = settings.intake_api_key.get_secret_value()
    by_key = bool(expected_key and x_api_key and hmac.compare_digest(x_api_key, expected_key))
    by_link = bool(expected_key and t and hmac.compare_digest(t, report_token(case_id)))
    if not (by_key or by_link):
        raise HTTPException(401, "This report link is not valid")
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
