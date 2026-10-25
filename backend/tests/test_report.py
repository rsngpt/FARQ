"""Police-portal evidence report."""

import pytest
from test_contract import TEXT_CLAIM

from farq.pipeline.runner import run_pipeline
from farq.report import report_html


def _done_case(client, repo, rules, media, queued, **answers):
    case_id = client.post("/cases", json=TEXT_CLAIM).json()["case_id"]
    if answers:
        client.patch(f"/cases/{case_id}/answers", json=answers)
    return run_pipeline(queued[0], repo, rules, media)


def test_report_has_the_evidence_trail(client, repo, rules, media, queued):
    case = _done_case(client, repo, rules, media, queued, claims_to_be="official",
                      asks_for="invest", money_sent=True)  # fmt: skip
    html = report_html(case)
    assert case.media_sha256 in html
    assert "farqdemo@okfakebank" in html and "9876543210" in html
    assert all(ev.id in html for ev in case.evidence)  # every finding, by ID
    assert "a government official" in html and "invest money" in html
    assert "FARQ does not submit it" in html and "1930" in html


def test_report_escapes_message_text(client, repo, rules, media, queued):
    """Text from a forwarded message must not become HTML in the report."""
    claim = TEXT_CLAIM | {"idempotency_key": "c_x",
                          "text": "<script>alert(1)</script> Call 98765 43210"}  # fmt: skip
    client.post("/cases", json=claim)
    case = run_pipeline(queued[0], repo, rules, media)
    assert "<script>" not in report_html(case)


def test_result_links_the_pdf_with_a_signature(client, repo, rules, media, queued, set_setting):
    from farq.api.reports import report_token

    set_setting("PUBLIC_BASE_URL", "https://example.trycloudflare.com/")
    case = _done_case(client, repo, rules, media, queued)
    pdf_url = client.get(f"/cases/{case.id}").json()["report"]["pdf_url"]
    assert pdf_url == (
        f"https://example.trycloudflare.com/cases/{case.id}/report.pdf?t={report_token(case.id)}"
    )


def test_pdf_needs_the_key_or_a_valid_signed_link(client, repo, rules, media, queued):
    from farq.api.reports import report_token

    case = _done_case(client, repo, rules, media, queued)
    path = f"/cases/{case.id}/report.pdf"
    no_key = {"X-API-Key": ""}
    assert client.get(path, headers=no_key).status_code == 401
    assert client.get(path + "?t=0123456789abcdef", headers=no_key).status_code == 401
    other = "00000000-0000-0000-0000-000000000000"  # a signature for another case
    assert client.get(f"{path}?t={report_token(other)}", headers=no_key).status_code == 401
    # The valid signature passes the check (the PDF itself needs WeasyPrint;
    # where it's missing, rendering fails after the check, not with 401).
    try:
        status = client.get(f"{path}?t={report_token(case.id)}", headers=no_key).status_code
    except OSError:
        status = "passed the check; WeasyPrint not installed here"
    assert status != 401


def test_pdf_endpoint_needs_a_finished_case(client):
    case_id = client.post("/cases", json=TEXT_CLAIM).json()["case_id"]
    assert client.get(f"/cases/{case_id}/report.pdf").status_code == 409


def test_pdf_renders(client, repo, rules, media, queued):
    """Needs WeasyPrint's system libraries (in the Docker image)."""
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("WeasyPrint's Pango libraries aren't installed here (they are in Docker)")
    case = _done_case(client, repo, rules, media, queued)
    response = client.get(f"/cases/{case.id}/report.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
