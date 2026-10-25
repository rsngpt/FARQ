"""Entities stage: collect phone numbers, UPI IDs and links (the scammer's side,
for the reply and the police report), and turn scam-pitch markers into weak
evidence.

On-screen text is checked first and trusted more: speech-to-text can drop a
digit from a spoken number, so entities heard in speech are marked "medium".
"""

from typing import Any

from farq.domain.casefile import Artifact, CaseFile, Evidence, Indicates, SourceType, Strength
from farq.entities import MARKER_REASONS, find_entities, find_markers
from farq.pipeline.stages import StageContext, StageOutput
from farq.text import normalise

CONFIDENCE = {"screen": "high", "speech": "medium"}


def entities(case: CaseFile, ctx: StageContext) -> StageOutput:
    passages = _passages(case)  # (source, time, text), screen first
    found: dict[tuple[str, str], dict[str, Any]] = {}
    markers: dict[str, dict[str, Any]] = {}

    for source, t, text, words in passages:
        for f in find_entities(text):
            at = _time_at(t, words, f.start)
            entry = found.setdefault(
                (f.kind, f.value),
                {"kind": f.kind, "value": f.value, "sources": [], "first_t": at},
            )
            entry["sources"].append({"source": source, "t": at, "snippet": f.snippet})
            entry["first_t"] = min(entry["first_t"], at)
        for m in find_markers(text):
            markers.setdefault(m.kind, {"kind": m.kind, "examples": []})["examples"].append(
                {
                    "source": source,
                    "t": _time_at(t, words, m.start),
                    "match": m.value,
                    "snippet": m.snippet,
                }
            )

    for entry in found.values():
        sources = {s["source"] for s in entry["sources"]}
        entry["confidence"] = "high" if sources & {"screen", "message"} else CONFIDENCE["speech"]

    evidence = [_marker_evidence(m) for m in markers.values()]
    upi_ids = [e for e in found.values() if e["kind"] == "upi_id"]
    if upi_ids:
        evidence.append(_upi_evidence(upi_ids))

    artifacts = []
    if passages:
        artifacts.append(
            Artifact(
                stage="entities",
                kind="entities",
                data={
                    "entities": sorted(found.values(), key=lambda e: e["first_t"]),
                    "markers": list(markers.values()),
                },
            )
        )
    return StageOutput(evidence=evidence, artifacts=artifacts)


Passage = tuple[str, float, str, list[dict[str, Any]]]  # source, time, text, word timings


def _passages(case: CaseFile) -> list[Passage]:
    passages: list[Passage] = []
    if (message := case.artifact("message")) is not None:  # a text claim
        passages.append(("message", 0.0, message.data["text"], []))
    if (ocr := case.artifact("ocr")) is not None:
        passages += [("screen", line["first_t"], line["text"], []) for line in ocr.data["lines"]]
    if (transcript := case.artifact("transcript")) is not None:
        passages += [
            ("speech", s["start"], s["text"], s.get("words", []))
            for s in transcript.data["segments"]
        ]
    return passages


def _time_at(start: float, words: list[dict[str, Any]], char_pos: int) -> float:
    """When the word at `char_pos` of a transcript segment was said. Whisper
    segments can span 10-15 s, so the segment start alone can be far off.
    Screen text has no word timings and keeps the time it first appeared."""
    pos = 0
    for w in words:
        pos += len(normalise(w["word"])) + 1  # +1 for the space between words
        if pos > char_pos:
            return w["start"]
    return start


def _marker_evidence(marker: dict[str, Any]) -> Evidence:
    first = min(marker["examples"], key=lambda e: e["t"])
    where = {
        "screen": f"on screen at {_clock(first['t'])}",
        "speech": f"in what is said at {_clock(first['t'])}",
        "message": "in the message",
    }[first["source"]]
    return Evidence(
        stage="entities",
        type=f"pitch_{marker['kind']}",
        source_type=SourceType.RULE,
        strength=Strength.WEAK,  # a warning sign; never decides on its own
        indicates=Indicates.SCAM,
        reason=f"{MARKER_REASONS[marker['kind']]} ({where})",
        details=marker,
    )


def _upi_evidence(upi_ids: list[dict[str, Any]]) -> Evidence:
    values = ", ".join(e["value"] for e in upi_ids)
    return Evidence(
        stage="entities",
        type="pitch_payment_id",
        source_type=SourceType.RULE,
        strength=Strength.WEAK,
        indicates=Indicates.SCAM,
        reason=f"It gives a UPI ID to pay into ({values}); official schemes don't ask for this.",
        details={"upi_ids": upi_ids},
    )


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"
