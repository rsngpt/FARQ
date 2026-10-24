"""The contract with Roshan's WhatsApp bot (FARQ backend integration guide)."""

from uuid import UUID

from sqlalchemy import select

from farq.pipeline.runner import run_pipeline
from farq.privacy import hash_user_id
from farq.storage.tables import CaseRow

BOT_FIELDS = {
    "media_type": "video",
    "idempotency_key": "c_m1a2b3c4",
    "user_ref": "a3efcbb07759f739",
    "caption": "Finance Minister ka naya scheme",
    "is_forwarded": "true",
    "frequently_forwarded": "false",
    "language": "hi",
    "received_at": "2026-10-24T16:20:00Z",
}
TEXT_CLAIM = {
    "media_type": "text",
    "text": "Guaranteed 40% returns in 3 months! Call 98765 43210, "
    "UPI farqdemo@okfakebank. Join our WhatsApp group today.",
    "idempotency_key": "c_text1",
    "user_ref": "a3efcbb07759f739",
    "is_forwarded": True,
    "frequently_forwarded": False,
    "language": "en",
    "received_at": "2026-10-24T16:20:00Z",
}
VERDICTS = {"CONFIRMED_SCAM", "LIKELY_SCAM", "NOT_VERIFIED"}


def test_bot_upload_is_queued_with_an_eta(client, queued, session, sample_video):
    body = client.post("/cases", files={"file": ("v.mp4", sample_video, "video/mp4")},
                       data=BOT_FIELDS).json()  # fmt: skip
    assert body["status"] == "queued" and body["eta_seconds"] > 0
    assert queued == [UUID(body["case_id"])]
    row = session.scalars(select(CaseRow)).one()
    assert (row.channel, row.message_id) == ("whatsapp", "c_m1a2b3c4")
    assert row.user_hash == hash_user_id("a3efcbb07759f739", "test-hash-key")  # hashed again
    assert row.context["caption"] == "Finance Minister ka naya scheme"
    assert row.context["is_forwarded"] is True


def test_same_idempotency_key_is_one_case(client, queued, sample_video):
    upload = {"file": ("v.mp4", sample_video, "video/mp4")}
    first = client.post("/cases", files=upload, data=BOT_FIELDS).json()
    second = client.post("/cases", files=upload, data=BOT_FIELDS).json()
    assert second["case_id"] == first["case_id"]
    assert len(queued) == 1


def test_queued_case_reports_its_status(client, sample_video):
    case_id = client.post("/cases", files={"file": ("v.mp4", sample_video, "video/mp4")},
                          data=BOT_FIELDS).json()["case_id"]  # fmt: skip
    assert client.get(f"/cases/{case_id}").json() == {"case_id": case_id, "status": "queued"}


def test_text_claim_gets_warning_signs_numbers_and_a_report(client, repo, rules, media, queued):
    case_id = client.post("/cases", json=TEXT_CLAIM).json()["case_id"]
    run_pipeline(queued[0], repo, rules, media)
    result = client.get(f"/cases/{case_id}").json()

    assert result["status"] == "done"
    assert result["verdict"] == "NOT_VERIFIED"  # weak signs alone never decide
    reasons = " ".join(r["text"] for r in result["reasons"])
    assert "guaranteed or risk-free returns" in reasons and "(in the message)" in reasons
    assert all(r["evidence_id"].startswith("ev_") for r in result["reasons"])
    assert {(e["kind"], e["value"]) for e in result["entities"]} >= {
        ("phone", "9876543210"), ("upi_id", "farqdemo@okfakebank")}  # fmt: skip
    assert result["report"]["available"] is True
    assert "farqdemo@okfakebank" in result["report"]["complaint_text"]
    assert result["original"] == {"found": False}
    assert (result["timeline_image_url"], result["campaign"], result["review"]) == (
        None,
        None,
        None,
    )


def test_answers_shape_the_result_even_after_the_verdict(client, repo, rules, media, queued):
    case_id = client.post("/cases", json=TEXT_CLAIM).json()["case_id"]
    run_pipeline(queued[0], repo, rules, media)
    before = client.get(f"/cases/{case_id}").json()
    assert not before["next_steps"][0].startswith("You have already paid")

    answers = {"claims_to_be": "official", "asks_for": "invest", "money_sent": True}
    response = client.patch(f"/cases/{case_id}/answers", json=answers)
    assert response.json() == {"status": "answers_recorded", "case_id": case_id}

    after = client.get(f"/cases/{case_id}").json()
    assert after["next_steps"][0].startswith("You have already paid: call 1930 now")
    text = after["report"]["complaint_text"]
    assert "claimed to be from official" in text and "asked me to invest" in text
    assert "I have already sent money." in text


def test_answers_must_be_one_of_the_bot_options(client):
    case_id = client.post("/cases", json=TEXT_CLAIM).json()["case_id"]
    bad = client.patch(f"/cases/{case_id}/answers", json={"claims_to_be": "the_president"})
    assert bad.status_code == 422


def test_result_never_says_genuine_and_uses_allowed_verdicts(client, repo, rules, media, queued):
    case_id = client.post("/cases", json=TEXT_CLAIM | {"idempotency_key": "c2",
                                                      "text": "Hello, see you tomorrow."}).json()[
        "case_id"
    ]  # fmt: skip
    run_pipeline(queued[0], repo, rules, media)
    result = client.get(f"/cases/{case_id}").json()
    assert result["verdict"] in VERDICTS
    flat = str(result).lower()
    assert "genuine." not in flat.replace("does not mean it is genuine.", "")
    assert "safe" not in flat and "authentic" not in flat
    assert result["report"]["available"] is False  # nothing to report
