"""Turn the source map and find-the-original results into Evidence rows.

A picture match on its own isn't a scam sign (people re-share genuine clips).
What matters is whether the picture and the voice belong together, and
whether the mouth was changed.
"""

from typing import Any

from farq.domain.casefile import Evidence, Indicates, Level, SourceType, Strength

TIME_TOLERANCE_S = 2.0  # same recording, but more than this apart = a different moment
WORDS_DIFFER = 0.3  # transcript similarity below this = different words
WORDS_SAME = 0.8


def clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def source_evidence(data: dict[str, Any]) -> list[Evidence]:
    out: list[Evidence] = []
    for comp in data.get("originals", []):
        seg = comp["segment"]
        title = seg["title"]
        span = (seg["start"], seg["end"])
        speech = [s for s in data.get("speech", [])
                  if s.get("clip_id") and s["start"] < span[1] and s["end"] > span[0]]  # fmt: skip
        words = comp.get("speech") or {}
        # "Same recording, different moment" needs precise timing (exact word
        # matches; "similar" matches are only placed to a 10-word window) AND the
        # original's own words at the aligned moment must differ. Seen in testing:
        # a squeezed genuine copy was flagged because a similar match landed
        # 2.8 s off the picture's moment.
        aligned_words_differ = words.get("similarity", 0.0) < WORDS_SAME
        elsewhere = [
            s for s in speech
            if s["clip_id"] != seg["clip_id"]
            or (s.get("method") == "exact" and aligned_words_differ
                and abs((s["clip_start"] - s["start"]) - comp["offset_s"]) > TIME_TOLERANCE_S)
        ]  # fmt: skip
        not_together = bool(elsewhere)

        if elsewhere:
            voice = elsewhere[0]
            out.append(Evidence(
                stage="source_map", type="not_recorded_together", source_type=SourceType.MATCH,
                strength=Strength.STRONG, indicates=Indicates.SCAM,
                reason=(f"The picture is from “{title}” ({clock(seg['clip_start'])}), but the "
                        f"voice is from “{voice['title']}” ({clock(voice['clip_start'])}): they "
                        "weren't recorded together."),
                details={"picture": seg, "voice": voice},
            ))  # fmt: skip
        elif words and not speech and words["similarity"] < WORDS_DIFFER:
            not_together = True
            out.append(Evidence(
                stage="source_map", type="words_differ_from_original",
                source_type=SourceType.MATCH, strength=Strength.STRONG, indicates=Indicates.SCAM,
                reason=(f"The picture matches “{title}” at {clock(seg['clip_start'])}, but the "
                        "words are different from what was said there."),
                details={"picture": seg, "speech": words},
            ))  # fmt: skip

        level = comp.get("mouth_level")
        altered = comp.get("altered") or []
        when = (f"from {clock(altered[0]['start'])} to {clock(altered[-1]['end'])}"
                if altered else "in places")  # fmt: skip
        model = {"model_name": "mouth-vs-face ratio (MediaPipe Face Landmarker)",
                 "model_version": comp.get("face_model_version")}  # fmt: skip
        if level == "high":
            out.append(Evidence(
                stage="source_map", type="mouth_altered", source_type=SourceType.MODEL,
                strength=Strength.STRONG, indicates=Indicates.SCAM, level=Level.HIGH,
                reason=(f"The lips were changed {when}; the rest of the face matches the "
                        f"original “{title}”."),
                details=comp, **model,
            ))  # fmt: skip
        elif level == "medium":
            out.append(Evidence(
                stage="source_map", type="mouth_altered", source_type=SourceType.MODEL,
                strength=Strength.WEAK, indicates=Indicates.SCAM, level=Level.MEDIUM,
                reason=f"The lips may have been changed {when} compared with “{title}”.",
                details=comp, **model,
            ))  # fmt: skip
        elif (
            level == "low"
            and not not_together
            and (words.get("similarity", 0) >= WORDS_SAME or speech)
        ):
            out.append(Evidence(
                stage="source_map", type="unaltered_copy", source_type=SourceType.MATCH,
                strength=Strength.STRONG, indicates=Indicates.NOT_SCAM, level=Level.LOW,
                reason=f"It matches “{title}” in our library without visible changes.",
                details=comp,
            ))  # fmt: skip
    return out
