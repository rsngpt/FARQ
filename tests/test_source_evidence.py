"""From source map and find-the-original results to evidence, verdict and reply."""

from farq.domain.casefile import Indicates, SourceType, Strength, Verdict
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage, StageOutput
from farq.sourcemap.evidence import source_evidence

PICTURE = {"start": 0.0, "end": 13.0, "clip_id": "A", "title": "Budget talk", "clip_start": 64.0}


def comp(mouth="unknown", altered=(), speech=None, offset=64.0):
    return {"segment": PICTURE, "offset_s": offset, "mouth_level": mouth,
            "altered": list(altered), "speech": speech, "face_model": "test"}  # fmt: skip


def voice(clip_id, title, start=0.5, end=12.7, clip_start=0.66):
    return {"start": start, "end": end, "clip_id": clip_id, "title": title,
            "clip_start": clip_start, "method": "exact"}  # fmt: skip


def types(evidence):
    return [(e.type, e.strength, e.indicates) for e in evidence]


def test_picture_and_voice_from_different_recordings():
    data = {"originals": [comp()], "speech": [voice("B", "College announcement")]}
    [e] = source_evidence(data)
    assert (e.type, e.source_type, e.strength, e.indicates) == (
        "not_recorded_together", SourceType.MATCH, Strength.STRONG, Indicates.SCAM)  # fmt: skip
    assert "“Budget talk” (1:04)" in e.reason and "“College announcement”" in e.reason


def test_same_recording_but_a_different_moment_is_not_together():
    data = {"originals": [comp()], "speech": [voice("A", "Budget talk", clip_start=200.0)]}
    assert types(source_evidence(data)) == [
        ("not_recorded_together", Strength.STRONG, Indicates.SCAM)
    ]


def test_unknown_voice_with_different_words():
    words = {"similarity": 0.1, "changes": []}
    data = {"originals": [comp(speech=words)], "speech": []}
    assert types(source_evidence(data)) == [
        ("words_differ_from_original", Strength.STRONG, Indicates.SCAM)
    ]


def test_mouth_levels():
    high = source_evidence({"originals": [comp("high", [{"start": 4, "end": 39}])]})
    assert types(high) == [("mouth_altered", Strength.STRONG, Indicates.SCAM)]
    assert "from 0:04 to 0:39" in high[0].reason
    assert high[0].source_type == SourceType.MODEL
    medium = source_evidence({"originals": [comp("medium")]})
    assert types(medium) == [("mouth_altered", Strength.WEAK, Indicates.SCAM)]


def test_unchanged_copy_points_away_from_scam():
    data = {"originals": [comp("low")], "speech": [voice("A", "Budget talk", clip_start=64.66)]}
    assert types(source_evidence(data)) == [("unaltered_copy", Strength.STRONG, Indicates.NOT_SCAM)]


def _verdict(repo, rules, media, new_case, data):
    seed = Stage("seed", "cpu", lambda c, x: StageOutput(evidence=source_evidence(data)))
    return run_pipeline(new_case(), repo, rules, media, [seed])


def test_lip_synced_collage_is_likely_scam_with_both_reasons(repo, rules, media, new_case):
    data = {"originals": [comp("high", [{"start": 4, "end": 12}])],
            "speech": [voice("B", "College announcement")]}  # fmt: skip
    case = _verdict(repo, rules, media, new_case, data)
    assert case.decision.verdict == Verdict.LIKELY_SCAM
    assert "weren't recorded together" in case.reply_text
    assert "lips were changed" in case.reply_text  # shown even though the rule didn't need it
    assert "reviewer" not in case.reply_text  # the reviewer flow was dropped
    assert "lips were changed" in case.reply_text


def test_plain_stitch_alone_is_likely_scam(repo, rules, media, new_case):
    """Picture and voice from different recordings rests on two independent
    matches, so on its own it gives LIKELY (team decision, 24 Oct)."""
    data = {"originals": [comp("unknown")], "speech": [voice("B", "College announcement")]}
    case = _verdict(repo, rules, media, new_case, data)
    assert case.decision.verdict == Verdict.LIKELY_SCAM
    assert case.decision.rule_id == "picture_voice_mismatch"
    assert "weren't recorded together" in case.reply_text.split("Why:")[1]


def test_words_differ_alone_still_does_not_decide(repo, rules, media, new_case):
    """Only the picture/voice mismatch got its own rule; other single signals don't."""
    data = {"originals": [comp(speech={"similarity": 0.1, "changes": []})], "speech": []}
    case = _verdict(repo, rules, media, new_case, data)
    assert case.decision.verdict == Verdict.NOT_VERIFIED


def test_unchanged_copy_is_still_never_called_genuine(repo, rules, media, new_case):
    data = {"originals": [comp("low")], "speech": [voice("A", "Budget talk", clip_start=64.66)]}
    case = _verdict(repo, rules, media, new_case, data)
    assert case.decision.verdict == Verdict.NOT_VERIFIED
    assert "matches “Budget talk” in our library without visible changes" in case.reply_text
    assert "doesn't prove what it says is true" in case.reply_text
    assert "genuine." not in case.reply_text.replace("does not mean it is genuine.", "")
