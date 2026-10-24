"""The result format Roshan's WhatsApp bot renders (FARQ backend integration
guide, section 3). Built when the case is read, so guided answers that arrive
after the verdict (e.g. money already sent) still shape the reply.

Rules from the contract: verdict is CONFIRMED_SCAM | LIKELY_SCAM | NOT_VERIFIED;
never "genuine", "real" or "safe"; no raw scores or percentages, only levels.
Dropped features (campaigns, reviewer, timeline image) are returned as null.
"""

from typing import Any

from farq.domain.casefile import CaseFile, CaseStatus, Evidence, Verdict

MAX_REASONS = 4

STAGE_LABELS = {
    "ingest": "reading_media",
    "lookup": "checking_known_fakes",
    "ocr": "reading_on_screen_text",
    "transcribe": "listening",
    "entities": "finding_numbers_and_links",
    "source_map": "checking_sources",
    "verify": "checking_sources",
    "analyse": "analysing",
}

HEADLINES = {
    Verdict.CONFIRMED_SCAM: "This is a known scam video.",
    Verdict.LIKELY_SCAM: "This looks like a scam.",
    Verdict.NOT_VERIFIED: "We could not verify this.",
}
ALTERED_HEADLINE = "This video has been altered."

NEXT_STEPS = {
    Verdict.CONFIRMED_SCAM: [
        "Do not call the number, click the link or pay anything.",
        "Report it at cybercrime.gov.in or call 1930.",
    ],
    Verdict.LIKELY_SCAM: [
        "Do not call the number, click the link or pay anything.",
        "Report it at cybercrime.gov.in or call 1930.",
    ],
    Verdict.NOT_VERIFIED: [
        "Do not act on it until you have checked with the official source.",
        "If in doubt, call 1930 (National Cyber Crime Helpline).",
    ],
}
MONEY_SENT_STEP = "You have already paid: call 1930 now to freeze the money, and tell your bank."

ALTERATION_TYPES = {"not_recorded_together", "words_differ_from_original", "mouth_altered"}
MAX_SWAP_WORDS = 6

# Guided answers in plain words for the complaint text ("" = leave it out).
CLAIMS_TO_BE = {
    "official": "a government official",
    "famous_expert": "a famous expert",
    "bank_upi": "a bank or UPI service",
    "family_friend": "a family member or friend",
    "company_boss": "my company or boss",
    "not_sure": "",
}
ASKS_FOR = {
    "invest": "invest money",
    "send_money": "send money",
    "otp_link_kyc": "share an OTP, open a link or do KYC",
    "nothing_yet": "",
}


def status_of(case: CaseFile) -> dict[str, Any]:
    if case.status == CaseStatus.DECIDED:
        return {"case_id": str(case.id), "status": "done"}
    if case.status == CaseStatus.FAILED:
        return {"case_id": str(case.id), "status": "failed"}
    if case.status == CaseStatus.RECEIVED or not case.timings:
        return {"case_id": str(case.id), "status": "queued"}
    last = case.timings[-1].stage
    return {"case_id": str(case.id), "status": "processing",
            "stage": STAGE_LABELS.get(last, "analysing")}  # fmt: skip


def build_result(case: CaseFile) -> dict[str, Any]:
    if case.decision is None:
        return status_of(case)
    verdict = case.decision.verdict
    cited = sorted(case.evidence_by_ids(case.decision.evidence_ids),
                   key=lambda e: e.strength.rank, reverse=True)  # fmt: skip
    altered = [e for e in case.evidence if e.type in ALTERATION_TYPES]
    copy = next((e for e in case.evidence if e.type == "unaltered_copy"), None)

    headline = HEADLINES[verdict]
    if altered and verdict != Verdict.NOT_VERIFIED:
        headline = ALTERED_HEADLINE
    if verdict == Verdict.NOT_VERIFIED and _ingest_failed(case):
        headline = "We couldn't open this file. Please forward the original again."

    return {
        "case_id": str(case.id),
        "status": "done",
        "verdict": verdict.value.upper(),
        "headline": headline,
        "summary": _summary(verdict, cited, copy),
        "reasons": [{"text": e.reason, "evidence_id": e.id} for e in cited[:MAX_REASONS]],
        "signals": [
            {"name": e.type, "level": e.level.value, "explanation": e.reason}
            for e in case.evidence
            if e.level is not None and e.type != "unaltered_copy"
        ],
        "original": _original(case),
        "source_map": _source_map(case),
        "entities": _entities(case),
        "next_steps": _next_steps(case, verdict),
        "report": _report(case, verdict, cited),
        "timeline_image_url": None,  # dropped for the demo
        "campaign": None,  # dropped
        "review": None,  # dropped
    }


def _summary(verdict: Verdict, cited: list[Evidence], copy: Evidence | None) -> str:
    if any(e.type == "not_recorded_together" for e in cited):
        return "The face and the voice in this video were not recorded together."
    if verdict == Verdict.NOT_VERIFIED:
        if copy is not None:
            return f"{copy.reason} That alone doesn't prove what it says is true."
        return "That does not mean it is genuine."
    return cited[0].reason if cited else HEADLINES[verdict]


def _original(case: CaseFile) -> dict[str, Any]:
    source_map = case.artifact("source_map")
    originals = source_map.data.get("originals", []) if source_map else []
    if not originals:
        return {"found": False}
    best = originals[0]
    seg = best["segment"]
    changes = (best.get("speech") or {}).get("changes", [])
    return {
        "found": True,
        "title": seg["title"],
        "url": None,
        "date": None,
        "at_s": round(seg["clip_start"], 1),
        # Only short word swaps; when the voice is from another recording the
        # words differ wholesale, and the reasons already say so.
        "changed_words": [
            {"original": c["original"], "fake": c["video"]}
            for c in changes
            if c["op"] == "replace"
            and len(c["original"].split()) <= MAX_SWAP_WORDS
            and len(c["video"].split()) <= MAX_SWAP_WORDS
        ][:5],
    }


def _source_map(case: CaseFile) -> list[dict[str, Any]]:
    source_map = case.artifact("source_map")
    if source_map is None:
        return []
    timeline = source_map.data.get("visual") or source_map.data.get("speech") or []
    return [
        {
            "start_s": round(s["start"], 1),
            "end_s": round(s["end"], 1),
            "source": s.get("title") or "No source found",
            "url": None,
        }
        for s in timeline
    ]


def _entities(case: CaseFile) -> list[dict[str, Any]]:
    """The scammer's side: numbers, UPI IDs and links found in the video."""
    found = case.artifact("entities")
    if found is None:
        return []
    return [
        {"kind": e["kind"], "value": e["value"], "confidence": e["confidence"]}
        for e in found.data["entities"]
    ]


def _next_steps(case: CaseFile, verdict: Verdict) -> list[str]:
    steps = list(NEXT_STEPS[verdict])
    if case.context.money_sent:
        steps.insert(0, MONEY_SENT_STEP)
    return steps


def _report(case: CaseFile, verdict: Verdict, cited: list[Evidence]) -> dict[str, Any]:
    """Pre-filled complaint text for the user to file on cybercrime.gov.in
    themselves (never auto-submitted). The evidence PDF comes next."""
    if verdict == Verdict.NOT_VERIFIED and not cited:
        return {"available": False, "complaint_text": None, "pdf_url": None}
    ctx = case.context
    lines = [
        f"On {case.created_at:%d %b %Y} I received a forwarded "
        f"{'video' if case.artifact('fingerprints') else 'message'} that "
        + (
            f"claimed to be from {CLAIMS_TO_BE[ctx.claims_to_be]}"
            if CLAIMS_TO_BE.get(ctx.claims_to_be or "")
            else "I believe is fraudulent"
        )  # fmt: skip
        + (
            f" and asked me to {ASKS_FOR[ctx.asks_for]}."
            if ASKS_FOR.get(ctx.asks_for or "")
            else "."
        ),  # fmt: skip
    ]
    if ctx.money_sent:
        lines.append("I have already sent money.")
    identifiers = [f"{e['kind'].replace('_', ' ')}: {e['value']}" for e in _entities(case)]
    if identifiers:
        lines.append("Identifiers in it: " + "; ".join(identifiers) + ".")
    if cited:
        lines.append("Checks by FARQ found: " + " ".join(e.reason for e in cited[:MAX_REASONS]))
    lines.append(f"File fingerprint (SHA-256): {case.media_sha256}.")
    return {"available": True, "complaint_text": " ".join(lines), "pdf_url": None}


def _ingest_failed(case: CaseFile) -> bool:
    return any(t.stage == "ingest" and t.status == "failed" for t in case.timings)
