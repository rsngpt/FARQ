"""Speech source map, using Whisper's real transcripts of the team's two
consented recordings as the library."""

from uuid import uuid4

import pytest

from farq.library import LibraryClip
from farq.sourcemap.speech import exact_matches, speech_map, words_of

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


def test_one_phrase_with_scattered_differences_is_one_segment(library):
    """Seen on the live stack: Whisper's transcript of a re-compressed fake
    differed from the library's in a few words, the exact matches came out in
    pieces, and each piece grew to the same span (listed 4 times)."""
    words = CONTROL.split()
    for i in (6, 13, 20, 27):  # a different word every 7, breaking the five-word lookups
        words[i] = "X"
    found = exact_matches(words_of(transcript(" ".join(words))), library)
    assert [(m["title"], m["words"]) for m in found] == [("control", len(words))]


def test_unrelated_speech_has_no_source(library):
    query = words_of(transcript("आज मौसम बहुत अच्छा है और हम पार्क में क्रिकेट खेलने जा रहे हैं शाम को"))
    assert exact_matches(query, library) == []


def test_a_few_shared_words_are_not_a_source(library):
    # "के बारे में" etc. appear in both recordings; short overlaps don't count.
    query = words_of(transcript("हम डिजिटल सेफटी के बारे में बात करेंगे कल शाम को"))
    assert exact_matches(query, library) == []


def _with_phrases(clips, embedder):
    from dataclasses import replace

    from farq.library import _embed_phrases

    return [replace(c, phrases=_embed_phrases(c.transcript, embedder)) for c in clips]


def test_reworded_speech_is_found_as_similar_not_exact(library, fake_embedder):
    clips = _with_phrases(library, fake_embedder)
    # The returns promise with words changed every few words, so no five words
    # in a row match the recording, but most words are shared.
    reworded = "इस स्कीम से आपको पक्का 40% रिटर्न मिलेगा केवल तीन महीने के अंदर"
    found = speech_map(transcript(reworded), clips, fake_embedder,
                       size=10, stride=5, min_similarity=0.5)  # fmt: skip
    matched = [s for s in found if s["clip_id"]]
    assert [(s["title"], s["method"]) for s in matched] == [("pitch", "similar")]
    assert matched[0]["clip_start"] == pytest.approx(12.5, abs=2.5)
    assert 0.5 <= matched[0]["similarity"] <= 1.0


def test_speech_map_marks_unmatched_speech(library, fake_embedder):
    clips = _with_phrases(library, fake_embedder)
    text = ("आज मौसम बहुत अच्छा है और हम पार्क में क्रिकेट खेलने जा रहे हैं "
            "नमस्ते कल कॉलेज ओडिटोरियम में सुबह 10 बजे एक वरक्शॉप है")  # fmt: skip
    found = speech_map(transcript(text), clips, fake_embedder,
                       size=10, stride=5, min_similarity=0.8)  # fmt: skip
    assert [(s["clip_id"] is None, s.get("title")) for s in found] == [
        (True, None),  # the weather talk: no source
        (False, "control"),
    ]
    assert found[0]["start"] == 0.0


def test_source_map_stage_maps_speech(repo, rules, media, new_case, session, fake_embedder):
    from farq.domain.casefile import Artifact, utcnow
    from farq.library import _embed_phrases
    from farq.pipeline.runner import run_pipeline
    from farq.pipeline.source_map import source_map
    from farq.pipeline.stages import Stage, StageOutput
    from farq.storage.tables import LibraryClipRow

    pitch = transcript(PITCH)
    session.add(LibraryClipRow(
        id=uuid4(), person="enrolled-1", title="pitch", source="test", consent_note=None,
        media_key="library/x/original.mp4", sha256="1" * 64, duration_s=30.0,
        fingerprints={"fps": 2.0, "frames": []}, transcript=pitch,
        phrases=_embed_phrases(pitch, fake_embedder), created_at=utcnow(),
    ))  # fmt: skip
    session.commit()
    heard = transcript("इस स्कीम में आपको गैरेंटीड 40% रिटर्न मिलेगा सिर्फ तीन महीने में", start=4.0)
    seed = Stage("seed", "gpu", lambda c, x: StageOutput(
        artifacts=[Artifact(stage="transcribe", kind="transcript", data=heard)]))  # fmt: skip
    case = run_pipeline(
        new_case(), repo, rules, media, [seed, Stage("source_map", "cpu", source_map)]
    )
    speech = case.artifact("source_map").data["speech"]
    assert [(s["title"], s["method"]) for s in speech] == [("pitch", "exact")]
    assert speech[0]["start"] == 4.0


@pytest.mark.real_models
def test_real_bge_m3_links_reworded_and_translated_phrases():
    """BGE-M3 itself (runs where the model is downloaded, e.g. in the container)."""
    from farq.embed import BgeM3Embedder
    from farq.settings import get_settings

    s = get_settings()
    if not (s.bge_m3_dir / "onnx" / "model.onnx_data").exists():
        pytest.skip("BGE-M3 not downloaded on this machine")
    vec = BgeM3Embedder(s.bge_m3_dir, s.bge_m3_revision).embed([
        "इस स्कीम में आपको गैरेंटीड 40% रिटर्न मिलेगा सिर्फ तीन महीने में",
        "इस स्कीम में आपको गारंटीड चालीस प्रतिशत रिटर्न मिलेगा तीन महीने में",
        "you will get guaranteed forty percent returns in just three months",
        "कल कॉलेज ओडिटोरियम में सुबह 10 बजे एक वर्कशॉप है",
    ])  # fmt: skip
    sims = vec @ vec[0]
    assert sims[1] >= s.similar_phrase_min  # reworded Hindi
    assert sims[2] >= s.similar_phrase_min  # English translation
    assert sims[3] < 0.5  # unrelated


def test_words_are_normalised_for_matching():
    words = words_of(transcript("UPI ID है, फर्कडेमो। ४0% रिटर्न!"))
    assert [w["w"] for w in words] == ["upi", "id", "है", "फर्कडेमो", "40%", "रिटर्न"]
