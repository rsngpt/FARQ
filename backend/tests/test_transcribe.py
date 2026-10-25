import wave
from io import BytesIO
from pathlib import Path

import pytest
from conftest import ffmpeg_make

from farq.pipeline.ingest import ingest
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage
from farq.pipeline.transcribe import transcribe
from farq.settings import REPO_ROOT, get_settings

INGEST_AND_TRANSCRIBE = [Stage("ingest", "cpu", ingest), Stage("transcribe", "gpu", transcribe)]


def test_stage_hears_the_16k_audio_and_stores_the_transcript(
    repo, rules, media, new_case, fake_asr, sample_video
):
    fake_asr.result = fake_asr.result | {"text": "namaste doston", "language": "hi"}
    case = run_pipeline(new_case(sample_video), repo, rules, media, INGEST_AND_TRANSCRIBE)

    [heard] = fake_asr.files_heard
    assert heard.name == "audio16k.wav"
    transcript = case.artifact("transcript")
    assert transcript.data["text"] == "namaste doston"
    assert (transcript.model_name, transcript.model_version) == ("fake-asr", "test")


def test_screenshot_has_nothing_to_hear(repo, rules, media, new_case, fake_asr, tmp_path):
    png = ffmpeg_make(tmp_path / "s.png", "-f", "lavfi", "-i", "testsrc", "-frames:v", "1")
    case = run_pipeline(new_case(png, ".png"), repo, rules, media, INGEST_AND_TRANSCRIBE)
    assert case.artifact("transcript") is None
    assert fake_asr.files_heard == []


def test_missing_model_fails_the_stage_with_a_clear_message(
    repo, rules, media, new_case, sample_video, monkeypatch, set_setting, tmp_path
):
    import farq.pipeline.transcribe as stage
    from farq.asr.engine import get_asr_engine

    monkeypatch.setattr(stage, "get_asr_engine", get_asr_engine)  # the real loader
    set_setting("WHISPER_MODEL_DIR", str(tmp_path / "nothing-here"))
    case = run_pipeline(new_case(sample_video), repo, rules, media, INGEST_AND_TRANSCRIBE)
    [timing] = [t for t in case.timings if t.stage == "transcribe"]
    assert timing.status == "failed"
    assert "run scripts/convert_whisper.py" in timing.error


CONTROL_CLIP = REPO_ROOT / "samples" / "clip2-plain.ogg"


@pytest.mark.real_models
def test_real_whisper_transcribes_the_control_clip(tmp_path: Path):
    """Uses the team's consented recording (git-ignored) and our converted model;
    skipped on machines that have neither."""
    from farq.asr.engine import WhisperEngine

    settings = get_settings()
    if not (settings.whisper_model_dir / "PROVENANCE.json").exists():
        pytest.skip("Whisper model not converted on this machine")
    if not CONTROL_CLIP.exists():
        pytest.skip("samples/clip2-plain.ogg not present")

    wav = tmp_path / "clip.wav"
    ffmpeg_make(wav, "-i", str(CONTROL_CLIP), "-ac", "1", "-ar", "16000")
    with wave.open(BytesIO(wav.read_bytes())) as w:
        assert w.getframerate() == 16000

    engine = WhisperEngine(settings.whisper_model_dir, settings.whisper_gpu_compute_type, 5)
    result = engine.transcribe(wav)
    print(engine.version, result["language"], result["text"])

    assert result["language"] in {"hi", "en", "ur"}  # Hindi/Hinglish speech
    assert result["speech_s"] > 5
    words = [w for s in result["segments"] for w in s["words"]]
    assert len(words) > 10
    starts = [w["start"] for w in words]
    assert starts == sorted(starts)  # word timings run forward
