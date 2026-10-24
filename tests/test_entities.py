"""Entity and pitch-marker extraction, checked against real outputs from this
project: PaddleOCR's lines from the overlay test video and Whisper's
transcripts of the team's consented recordings (docs/test-data)."""

from farq.domain.casefile import Artifact, Strength, Verdict
from farq.entities import find_entities, find_markers
from farq.pipeline.entities import entities
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage, StageOutput

# PaddleOCR output on the overlay test video (24 Oct 2026 run).
OCR_LINES = [
    {"text": "Call 98765 43210 UPl: farqdemo@okfakebank", "first_t": 0.0},
    {"text": "Guaranteed 40% returns in 3 months", "first_t": 0.0},
    {"text": "गारंटीड 40% रटिर्न सरिफ 3 महीने में", "first_t": 27.0},
    {"text": "WhatsApp गरुप जॉइन करें", "first_t": 27.0},
]
# Whisper output on clip 1 (mock scam pitch), split as it was into segments.
PITCH_SEGMENTS = [
    (0.0, "नमस्ते दोस्तों मैं राकेश महरा नैशनल वेल्थ पोर्ड की तरफ से बात कर रहा हूँ"),
    (8.4, "इस स्कीम में आपको गैरेंटीड 40% रिटर्न मिलेगा सिर्फ तीन महीने में"),
    (13.9, "यह ओफर सिर्फ इस हफते तक तो जल्दी की कीजिए"),
    (17.2, "रेजिस्टर करने के लिए हमारे वाटसप ग्रूप में जोइन कीजिए"),
    (21.0, "या सीधा कॉल कीजिए 987654320"),
    (25.6, "पेमेंट के लिए UPI ID है फर्कडेमो एट ओके फेक बैंक"),
    (37.1, "जादा जानकारी के लिए वेबसाइट देखिए bonus.example.com"),
]
# Whisper output on clip 2 (plain announcement, the control).
CONTROL_SEGMENTS = [
    (0.0, "नमस्ते कल कॉलेज ओडिटोरियम में सुबह 10 बजे एक वरक्शॉप है डिजिटल सेफटी के बारे में"),
    (6.2, "सब इस्टेंट्स आ सकते हैं रेजिट्रेशन की ज़रूरत नहीं हैं अपने दोस्तों को भी बताईए धन्यवाद"),
]


def _artifacts(ocr_lines=None, segments=None):
    out = []
    if ocr_lines is not None:
        out.append(Artifact(stage="ocr", kind="ocr", data={"lines": ocr_lines}))
    if segments is not None:
        segs = [{"start": t, "end": t + 3, "text": text, "words": []} for t, text in segments]
        out.append(Artifact(stage="transcribe", kind="transcript", data={"segments": segs}))
    return out


def _run(repo, rules, media, new_case, artifacts):
    seed = Stage("seed", "cpu", lambda case, ctx: StageOutput(artifacts=artifacts))
    return run_pipeline(new_case(), repo, rules, media, [seed, Stage("entities", "cpu", entities)])


def test_phone_upi_and_link_patterns():
    found = {(f.kind, f.value) for f in find_entities(OCR_LINES[0]["text"])}
    assert found == {("phone", "9876543210"), ("upi_id", "farqdemo@okfakebank")}
    assert [(f.kind, f.value) for f in find_entities("call +91-98765-43210 now")] == [
        ("phone", "9876543210")
    ]
    assert [f.value for f in find_entities("visit https://bonus.example.com/join")] == [
        "https://bonus.example.com/join"
    ]
    assert [f.kind for f in find_entities("join chat.whatsapp.com/AbC123")] == ["group_link"]


def test_emails_and_short_numbers_are_not_entities():
    assert find_entities("write to help@example.com") == []  # not a UPI ID, not a link
    assert find_entities("987654320") == []  # 9 digits: the spoken number Whisper cut short
    assert find_entities("call 12345 67890") == []  # Indian mobiles start 6-9


def test_markers_in_hindi_spellings_from_ocr_and_whisper():
    assert {m.kind for m in find_markers(OCR_LINES[2]["text"])} == {"guaranteed_returns"}
    assert {m.kind for m in find_markers(OCR_LINES[3]["text"])} == {"group_invite"}
    assert {m.kind for m in find_markers(PITCH_SEGMENTS[1][1])} == {"guaranteed_returns"}
    assert {m.kind for m in find_markers(PITCH_SEGMENTS[2][1])} == {"urgency"}
    assert {m.kind for m in find_markers(PITCH_SEGMENTS[3][1])} == {"group_invite"}


def test_scam_pitch_gives_entities_and_weak_warning_signs(repo, rules, media, new_case):
    case = _run(repo, rules, media, new_case, _artifacts(OCR_LINES, PITCH_SEGMENTS))
    data = case.artifact("entities").data
    by_value = {(e["kind"], e["value"]): e for e in data["entities"]}

    assert by_value[("phone", "9876543210")]["confidence"] == "high"  # read on screen
    assert by_value[("upi_id", "farqdemo@okfakebank")]["confidence"] == "high"
    link = by_value[("link", "bonus.example.com")]
    assert (link["confidence"], link["first_t"]) == ("medium", 37.1)  # heard, not seen
    assert ("phone", "987654320") not in by_value  # the incomplete spoken number

    types = {e.type for e in case.evidence}
    assert types == {
        "pitch_guaranteed_returns",
        "pitch_group_invite",
        "pitch_urgency",
        "pitch_payment_id",
    }
    assert all(e.strength == Strength.WEAK for e in case.evidence)
    # Weak signs alone never make a verdict: NOT VERIFIED, with the signs listed.
    assert case.decision.verdict == Verdict.NOT_VERIFIED
    assert "Warning signs:" in case.reply_text
    assert "guaranteed or risk-free returns" in case.reply_text
    assert "(on screen at 0:00)" in case.reply_text


def test_speech_markers_use_word_timings_not_segment_start(repo, rules, media, new_case):
    # One long Whisper segment (0-15 s) where the urgency phrase comes late.
    text = "नमस्ते दोस्तों आज एक स्कीम है यह ओफर सिर्फ इस हफते तक"
    words = [
        {"word": w, "start": float(i), "end": float(i) + 1} for i, w in enumerate(text.split())
    ]
    segment = [{"start": 0.0, "end": 15.0, "text": text, "words": words}]
    seed = Artifact(stage="transcribe", kind="transcript", data={"segments": segment})
    case = _run(repo, rules, media, new_case, [seed])
    [urgency] = case.evidence
    assert urgency.type == "pitch_urgency"
    assert "(in what is said at 0:08)" in urgency.reason  # "सिर्फ" is word 8, not 0:00


def test_control_clip_has_no_entities_or_markers(repo, rules, media, new_case):
    case = _run(repo, rules, media, new_case, _artifacts(segments=CONTROL_SEGMENTS))
    assert case.artifact("entities").data == {"entities": [], "markers": []}
    assert case.evidence == []
    assert "Warning signs:" not in case.reply_text


def test_nothing_to_read_or_hear_gives_no_artifact(repo, rules, media, new_case):
    case = _run(repo, rules, media, new_case, _artifacts())
    assert case.artifact("entities") is None
