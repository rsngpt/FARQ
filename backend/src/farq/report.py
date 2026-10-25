"""Police-portal evidence report (PDF) for the user to attach when they file a
complaint at cybercrime.gov.in themselves. FARQ never submits it.

Built from the same result the WhatsApp bot shows, plus the evidence trail:
evidence IDs with times, identifiers found, the file's SHA-256, and the tools
and model versions used. No raw scores: findings and levels only.
"""

from datetime import UTC, datetime
from html import escape
from typing import Any

from farq.api.result import ASKS_FOR, CLAIMS_TO_BE, build_result
from farq.domain.casefile import CaseFile

SOURCE_TYPES = {"match": "Library / known-fake match", "model": "Measurement (model)",
                "rule": "Rule check"}  # fmt: skip
WHERE = {"screen": "on screen", "speech": "spoken", "message": "in the message"}


def report_html(case: CaseFile) -> str:
    result = build_result(case)
    ctx = case.context
    e = escape

    def row(*cells: Any) -> str:
        return "<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in cells) + "</tr>"

    reasons = {r["evidence_id"] for r in result["reasons"]}
    evidence_rows = "".join(
        row(
            ev.id,
            ev.reason,
            SOURCE_TYPES.get(ev.source_type, ev.source_type),
            f"{ev.created_at:%d %b %Y %H:%M:%S} UTC",
        )  # fmt: skip
        for ev in case.evidence
        if ev.id in reasons or ev.indicates == "scam"
    )
    found = case.artifact("entities")
    identifier_rows = "".join(
        row(
            i["kind"].replace("_", " "),
            i["value"],
            ", ".join(sorted({WHERE.get(s["source"], s["source"]) for s in i["sources"]})),
            i["confidence"],
        )  # fmt: skip
        for i in (found.data["entities"] if found else [])
    )
    map_rows = "".join(
        row(f"{s['start_s']:.1f}–{s['end_s']:.1f} s", s["source"]) for s in result["source_map"]
    )
    original = result["original"]
    changed = "".join(row(c["original"], c["fake"]) for c in original.get("changed_words", []))
    versions = sorted(
        {f"{a.model_name} {a.model_version}" for a in case.artifacts if a.model_name}
        | {f"{ev.model_name} {ev.model_version}" for ev in case.evidence if ev.model_name}
    )
    answers = [
        ("Claimed to be from", CLAIMS_TO_BE.get(ctx.claims_to_be or "") or "—"),
        ("Asked the user to", ASKS_FOR.get(ctx.asks_for or "") or "—"),
        ("Money already sent", {True: "Yes", False: "No"}.get(ctx.money_sent, "—")),
        ("Forwarded", {True: "Yes", False: "No"}.get(ctx.is_forwarded, "—")),
        ("Received", ctx.received_at or f"{case.created_at:%d %b %Y %H:%M} UTC"),
    ]
    complaint = result["report"]["complaint_text"] or "No complaint text: nothing to report."

    def table(headers: list[str], rows: str, empty: str) -> str:
        if not rows:
            return f"<p class='muted'>{e(empty)}</p>"
        head = "".join(f"<th>{e(h)}</th>" for h in headers)
        return f"<table><tr>{head}</tr>{rows}</table>"

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 16mm; @bottom-center {{ content: "FARQ evidence report · page "
  counter(page) " of " counter(pages); font-size: 8pt; color: #666; }} }}
body {{ font-family: "DejaVu Sans", "Lohit Devanagari", sans-serif; font-size: 10pt; color: #111; }}
h1 {{ font-size: 17pt; margin: 0; }} h2 {{ font-size: 12pt; margin: 6mm 0 2mm; color: #0f5e6b; }}
.muted {{ color: #555; }} .verdict {{ font-size: 13pt; font-weight: bold; }}
.box {{ border: 1px solid #bbb; padding: 3mm; background: #f5f7f8; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #ccc; padding: 1.5mm; text-align: left; vertical-align: top; }}
th {{ background: #eef2f4; font-size: 9pt; }}
.mono {{ font-family: "DejaVu Sans Mono", monospace; font-size: 8.5pt; word-break: break-all; }}
</style></head><body>
<h1>FARQ evidence report</h1>
<p class="muted">Case {e(str(case.id))} · generated {datetime.now(UTC):%d %b %Y %H:%M} UTC.
For the person who received this message to attach when filing a complaint at
cybercrime.gov.in. FARQ does not submit it. This is an automated check, not a legal finding.</p>

<h2>Result</h2>
<p class="verdict">{e(result["verdict"].replace("_", " "))}: {e(result["headline"])}</p>
<p>{e(result["summary"])}</p>

<h2>Pre-filled complaint text</h2>
<div class="box">{e(complaint)}</div>

<h2>What the recipient told us</h2>
{table(["Question", "Answer"], "".join(row(q, a) for q, a in answers), "")}

<h2>Findings (evidence)</h2>
{
        table(
            ["Evidence ID", "Finding", "Kind of check", "Recorded"],
            evidence_rows,
            "No scam signs were found.",
        )
    }

<h2>Phone numbers, UPI IDs and links in the message</h2>
{table(["Kind", "Value", "Where", "Confidence"], identifier_rows, "None found.")}

<h2>Where the video came from</h2>
{table(["Part of the video", "Source"], map_rows, "Not checked or not a video.")}
{
        "<p>Original recording: " + e(original["title"]) + f" (at {original['at_s']:.0f} s).</p>"
        if original.get("found")
        else ""
    }
{table(["Original said", "This video says"], changed, "") if changed else ""}

<h2>File and tools</h2>
<p>SHA-256 of the file as received: <span class="mono">{e(case.media_sha256)}</span><br>
Size: {case.media_bytes:,} bytes · Case created {case.created_at:%d %b %Y %H:%M:%S} UTC</p>
<p class="muted">Tools and model versions: {e("; ".join(versions) or "—")}</p>

<h2>If money was sent</h2>
<p>Call <b>1930</b> (National Cyber Crime Helpline) immediately and tell your bank, so the
money can be frozen.</p>
</body></html>"""


def report_pdf(case: CaseFile) -> bytes:
    from weasyprint import HTML  # needs Pango; available in the Docker image

    return HTML(string=report_html(case)).write_pdf()
