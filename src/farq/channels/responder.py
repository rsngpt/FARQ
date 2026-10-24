"""Turns a decision into the reply a user reads. Plain text for now; channel
adapters (Telegram, WhatsApp) will add buttons and formatting on top."""

from farq.domain.casefile import CaseFile, Decision, StageStatus, Verdict

MAX_REASONS = 4

UNREADABLE = (
    "We couldn't open this file, so we could not check it. Please forward the "
    "original video, voice note or screenshot again."
)

HELPLINE = "call 1930 (National Cyber Crime Helpline) or report at cybercrime.gov.in"

HEADLINES = {
    Verdict.CONFIRMED_SCAM: "This video is a known scam.",
    Verdict.LIKELY_SCAM: "This looks like a scam. A reviewer is checking it.",
    Verdict.NOT_VERIFIED: "We could not verify this video. That does not mean it is genuine.",
}

NEXT_STEPS = {
    Verdict.CONFIRMED_SCAM: f"Do not send money or share OTPs. To report it, {HELPLINE}.",
    Verdict.LIKELY_SCAM: f"Do not send money or share OTPs. To report it, {HELPLINE}.",
    Verdict.NOT_VERIFIED: (
        "Do not act on it until you have checked with the official source. "
        f"If in doubt, {HELPLINE}."
    ),
}


def compose_reply(case: CaseFile, decision: Decision) -> str:
    lines: list[str] = []
    if case.context.money_sent:
        lines += [
            "If you have already sent money: call 1930 now and tell your bank.",
            "",
        ]
    headline = HEADLINES[decision.verdict]
    if decision.verdict == Verdict.NOT_VERIFIED and _ingest_failed(case):
        headline = UNREADABLE
    lines += [f"Verdict: {decision.verdict.label}", headline]

    cited = case.evidence_by_ids(decision.evidence_ids)
    cited.sort(key=lambda e: e.strength.rank, reverse=True)  # strongest first
    reasons = [e.reason for e in cited][:MAX_REASONS]
    if reasons:
        heading = "Warning signs:" if decision.verdict == Verdict.NOT_VERIFIED else "Why:"
        lines += ["", heading, *(f"- {r}" for r in reasons)]

    copies = [e for e in case.evidence if e.type == "unaltered_copy"]
    if copies and decision.verdict == Verdict.NOT_VERIFIED:
        lines += ["", f"{copies[0].reason} That alone doesn't prove what it says is true."]

    lines += ["", NEXT_STEPS[decision.verdict]]
    return "\n".join(lines)


def _ingest_failed(case: CaseFile) -> bool:
    return any(t.stage == "ingest" and t.status == StageStatus.FAILED for t in case.timings)
