"""OCR stage: read on-screen text from a sample of keyframes. Scam videos put
phone numbers, UPI IDs, links and return promises on screen, often more
reliably than they say them, so this runs before speech-to-text."""

from difflib import SequenceMatcher
from typing import Any

from farq.domain.casefile import Artifact, CaseFile
from farq.ocr.engine import OcrEngine, TextLine, get_ocr_engine
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings
from farq.text import compare_key, normalise

# Two readings this similar are the same overlay seen in different frames.
SAME_TEXT = 0.85


def ocr(case: CaseFile, ctx: StageContext, engine: OcrEngine | None = None) -> StageOutput:
    keyframes = case.artifact("keyframes")
    if keyframes is None:
        return StageOutput()  # voice note: nothing on screen
    settings = get_settings()
    engine = engine or get_ocr_engine(settings.ocr_det_side)

    chosen = spread(keyframes.data["frames"], settings.ocr_max_frames)
    paths = []
    for i, frame in enumerate(chosen):
        path = ctx.workdir / f"{i:05d}.jpg"
        ctx.media.download(frame["key"], path)
        paths.append(path)

    lines = merge_lines(
        [(f["t"], read) for f, read in zip(chosen, engine.read(paths), strict=True)],
        min_score=settings.ocr_min_score,
    )
    return StageOutput(
        artifacts=[
            Artifact(
                stage="ocr",
                kind="ocr",
                data={
                    "lines": lines,
                    "frames_read": len(chosen),
                    "frames_available": len(keyframes.data["frames"]),
                },
                model_name=engine.name,
                model_version=engine.version,
            )
        ]
    )


def spread(items: list[Any], limit: int) -> list[Any]:
    """At most `limit` items, evenly spaced, always including the first."""
    if len(items) <= limit:
        return list(items)
    step = len(items) / limit
    return [items[int(i * step)] for i in range(limit)]


def merge_lines(
    frames: list[tuple[float, list[TextLine]]], *, min_score: float
) -> list[dict[str, Any]]:
    """Turn per-frame readings into distinct lines of text, each with when it was
    first and last seen. Drops low-confidence readings and single characters."""
    merged: list[dict[str, Any]] = []
    for t, readings in frames:
        for line in readings:
            text = normalise(line.text)
            key = compare_key(text)
            if line.score < min_score or len(key) < 2:
                continue
            same = next(
                (m for m in merged if SequenceMatcher(None, m["_key"], key).ratio() >= SAME_TEXT),
                None,
            )
            if same is None:
                merged.append(
                    {"_key": key, "text": text, "score": round(line.score, 3),
                     "first_t": t, "last_t": t, "frames": 1, "box": line.box}
                )  # fmt: skip
                continue
            same["last_t"] = max(same["last_t"], t)
            same["frames"] += 1
            if line.score > same["score"]:  # keep the clearest reading
                same.update(text=text, score=round(line.score, 3), box=line.box)
    for m in merged:
        del m["_key"]
    return sorted(merged, key=lambda m: m["first_t"])
