import wave
from io import BytesIO

import pytest
from conftest import ffmpeg_make, synthetic_video

from farq.domain.casefile import StageStatus, Verdict
from farq.pipeline.ingest import ingest
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage

ONLY_INGEST = [Stage("ingest", "cpu", ingest)]


@pytest.fixture
def run_ingest(repo, rules, media, new_case):
    """Run just the ingest stage on new media; return the finished CaseFile."""

    def _run(content: bytes, extension: str = ".mp4"):
        return run_pipeline(new_case(content, extension), repo, rules, media, ONLY_INGEST)

    return _run


def _wav(media, key):
    with wave.open(BytesIO(media.objects[key])) as w:
        return w.getframerate(), w.getnchannels(), w.getnframes() / w.getframerate()


def test_video_gives_media_info_keyframes_and_16k_audio(run_ingest, media, sample_video):
    case = run_ingest(sample_video)
    assert case.timings[0].status == StageStatus.OK

    info = case.artifact("media_info").data
    assert info["kind"] == "video"
    assert info["duration_s"] == pytest.approx(3, abs=0.2)
    assert info["video"]["width"] == 320

    frames = case.artifact("keyframes").data["frames"]
    assert [f["t"] for f in frames] == pytest.approx([0, 1, 2], abs=0.15)
    assert all(media.objects[f["key"]].startswith(b"\xff\xd8") for f in frames)  # JPEGs

    audio = case.artifact("audio_16k")
    rate, channels, seconds = _wav(media, audio.storage_key)
    assert (rate, channels) == (16000, 1)
    assert seconds == pytest.approx(3, abs=0.2)
    assert case.artifact("media_info").model_name == "ffmpeg"


def test_long_video_is_sampled_evenly(run_ingest, set_setting, tmp_path):
    set_setting("MAX_KEYFRAMES", "4")
    frames = run_ingest(synthetic_video(tmp_path / "long.mp4", seconds=8)).artifact("keyframes")
    assert [f["t"] for f in frames.data["frames"]] == pytest.approx([0, 2, 4, 6], abs=0.3)


def test_only_the_first_max_seconds_are_processed(run_ingest, media, set_setting, tmp_path):
    set_setting("MAX_MEDIA_SECONDS", "2")
    case = run_ingest(synthetic_video(tmp_path / "four.mp4", seconds=4))
    assert case.artifact("media_info").data["processed_s"] == 2
    assert len(case.artifact("keyframes").data["frames"]) == 2
    assert _wav(media, case.artifact("audio_16k").storage_key)[2] == pytest.approx(2, abs=0.1)


def test_screenshot_gives_one_keyframe_and_no_audio(run_ingest, tmp_path):
    png = ffmpeg_make(
        tmp_path / "shot.png", "-f", "lavfi", "-i", "testsrc=size=640x360", "-frames:v", "1"
    )
    case = run_ingest(png, ".png")
    assert case.artifact("media_info").data["kind"] == "image"
    assert case.artifact("keyframes").data["frames"][0]["t"] == 0
    assert case.artifact("audio_16k") is None


def test_voice_note_gives_audio_and_no_keyframes(run_ingest, tmp_path):
    voice = ffmpeg_make(
        tmp_path / "voice.ogg", "-f", "lavfi", "-i", "sine=duration=2", "-c:a", "libopus"
    )
    case = run_ingest(voice, ".ogg")
    assert case.artifact("media_info").data["kind"] == "audio"
    assert case.artifact("keyframes") is None
    assert case.artifact("audio_16k") is not None


def test_video_without_sound_has_no_audio_artifact(run_ingest, tmp_path):
    silent = synthetic_video(tmp_path / "silent.mp4", seconds=2, with_audio=False)
    assert run_ingest(silent).artifact("audio_16k") is None


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("text file", b"this is just text"),
        # A concat list would make FFmpeg read another file on the server.
        ("concat trap", b"ffconcat version 1.0\nfile '/etc/hostname'\n"),
        # A playlist would make FFmpeg fetch from the internet.
        ("playlist trap", b"#EXTM3U\n#EXTINF:2,\nhttp://example.com/a.ts\n#EXT-X-ENDLIST\n"),
    ],
)
def test_non_media_and_trap_files_fail_the_stage(run_ingest, name, content):
    case = run_ingest(content)
    [timing] = case.timings[:1]
    assert timing.status == StageStatus.FAILED
    assert "could not read the file" in timing.error
    assert case.artifacts == []
    # The user is told plainly that the file couldn't be opened.
    assert "We couldn't open this file" in case.reply_text
    assert case.decision.verdict == Verdict.NOT_VERIFIED


def test_readable_file_keeps_the_normal_not_verified_wording(run_ingest, sample_video):
    reply = run_ingest(sample_video).reply_text
    assert "does not mean it is genuine" in reply
    assert "couldn't open" not in reply


def test_stored_file_that_changed_since_upload_fails(repo, rules, media, new_case, sample_video):
    case_id = new_case(sample_video, sha256="0" * 64)
    case = run_pipeline(case_id, repo, rules, media, ONLY_INGEST)
    assert case.timings[0].status == StageStatus.FAILED
    assert "fingerprint" in case.timings[0].error
