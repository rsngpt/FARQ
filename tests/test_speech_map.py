"""Speech source map, using Whisper's real transcripts of the team's two
consented recordings as the library."""

from uuid import uuid4

import pytest

from farq.library import LibraryClip
from farq.sourcemap.speech import exact_matches, words_of

PITCH = (
    "नमस्ते दोस्तों मैं राकेश महरा नैशनल वेल्थ पोर्ड की तरफ से बात कर रहा हूँ "
    "आज मैं आपको एक स्पेशल स्कीम के बारे में बताऊंगा "
    "इस स्कीम में आपको गैरेंटीड 40% रिटर्न मिलेगा सिर्फ तीन महीने में "
    "यह ओफर सिर्फ इस हफते तक तो जल्दी की कीजिए"
)
CONTROL = (
    "नमस्ते कल कॉलेज ओडिटोरियम में सुबह 10 बजे एक वरक्शॉप है डिजिटल सेफटी के बारे में "
    "सब इस्टेंट्स आ सकते हैं रेजिट्रेशन की ज़रूरत नहीं हैं अपने दोस्तों को भी बताईए धन्यवाद"
)


def transcript(text: str, start: float = 0.0, step: float = 0.5) -> dict:
    """A transcript in Whisper's shape, one word every `step` seconds."""
    words = [
        {"word": w, "start": start + i * step, "end": start + i * step + step * 0.8, "p": 0.9}
        for i, w in enumerate(text.split())
    ]
    return {"segments": [{"start": start, "end": words[-1]["end"], "text": text, "words": words}]}


def clip(title: str, text: str) -> LibraryClip:
    return LibraryClip(uuid4(), "enrolled-1", title, "test", 60.0, {"frames": []}, transcript(text))


@pytest.fixture
def library():
    return [clip("pitch", PITCH), clip("control", CONTROL)]


def test_collage_speech_maps_each_phrase_to_its_recording(library):
    # First half of the control sentence, then the returns promise from the
    # pitch, with one word spelled the other way (as a second Whisper run might).
    from_control = "नमस्ते कल कॉलेज ओडिटोरियम में सुबह 10 बजे एक वरक्शॉप है"
    from_pitch = "इस स्कीम में आपको गारंटीड 40% रिटर्न मिलेगा सिर्फ तीन महीने में"
    query = words_of(transcript(f"{from_control} {from_pitch}", start=0.0))

    found = exact_matches(query, library)
    assert [(m["title"], m["method"]) for m in found] == [("control", "exact"), ("pitch", "exact")]
    control, pitch = found
    assert control["start"] == 0.0 and control["clip_start"] == 0.0
    assert pitch["start"] == pytest.approx(5.5)  # word 11 of the query
    assert pitch["clip_start"] == pytest.approx(12.5)  # word 25 of the pitch recording
    assert pitch["words"] == 12  # the whole phrase, across the spelling slip
    assert control["words"] == 11


def test_unrelated_speech_has_no_source(library):
    query = words_of(transcript("आज मौसम बहुत अच्छा है और हम पार्क में क्रिकेट खेलने जा रहे हैं शाम को"))
    assert exact_matches(query, library) == []


def test_a_few_shared_words_are_not_a_source(library):
    # "के बारे में" etc. appear in both recordings; short overlaps don't count.
    query = words_of(transcript("हम डिजिटल सेफटी के बारे में बात करेंगे कल शाम को"))
    assert exact_matches(query, library) == []


def test_words_are_normalised_for_matching():
    words = words_of(transcript("UPI ID है, फर्कडेमो। ४0% रिटर्न!"))
    assert [w["w"] for w in words] == ["upi", "id", "है", "फर्कडेमो", "40%", "रिटर्न"]
