"""Find-the-original on synthetic video, with a stand-in face finder that
reports fixed mouth and face boxes (real faces need the team's clips)."""

from pathlib import Path

import pytest
from conftest import ffmpeg_make

from farq.media.ffmpeg import read_frames
from farq.sourcemap.original import (
    ORIGINAL_FPS,
    QUERY_FPS,
    altered_spans,
    analyse_segment,
    compare_speech,
    mouth_level,
)

SIZE = (640, 360)
MOUTH = (280, 220, 360, 260)  # where the stand-in says the mouth is
FACE = (200, 100, 440, 320)


class FixedFaceFinder:
    name = "fixed-boxes"
    version = "test"

    def regions(self, rgb):
        return MOUTH, FACE


@pytest.fixture(scope="module")
def videos(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("original")
    original = d / "original.mp4"
    ffmpeg_make(original, "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25", "-t", "10",
                "-pix_fmt", "yuv420p")  # fmt: skip
    # A copy that starts 2.2 s into the original, smaller and re-compressed.
    plain = d / "copy.mp4"
    ffmpeg_make(plain, "-ss", "2.2", "-i", str(original), "-t", "4", "-vf", "scale=480:270",
                "-c:v", "libx264", "-crf", "30")  # fmt: skip
    # The same copy with the "mouth" painted over from 1 s to 3 s only.
    x0, y0, x1, y1 = (int(v * 0.75) for v in MOUTH)  # boxes scaled to 480x270
    edited = d / "edited.mp4"
    ffmpeg_make(edited, "-ss", "2.2", "-i", str(original), "-t", "4", "-vf",
                f"scale=480:270,drawbox=x={x0}:y={y0}:w={x1 - x0}:h={y1 - y0}:"
                "color=red@1:t=fill:enable='between(t,1,3)'",
                "-c:v", "libx264", "-crf", "30")  # fmt: skip
    return {"original": original, "copy": plain, "edited": edited}


def _analyse(videos, which: str):
    segment = {"start": 0.0, "end": 4.0, "clip_start": 2.0}  # coarse, to the half second
    lead_in = 0.5
    query = read_frames(videos[which], start=0, duration=4, fps=QUERY_FPS, size=SIZE, timeout=60)
    original = read_frames(
        videos["original"], start=segment["clip_start"] - lead_in, duration=4 + 2 * lead_in,
        fps=ORIGINAL_FPS, size=SIZE, timeout=60,
    )  # fmt: skip
    return analyse_segment(segment, query, original, FixedFaceFinder(), lead_in_s=lead_in)


def test_alignment_corrects_the_coarse_offset(videos):
    result = _analyse(videos, "copy")
    assert result["offset_s"] == pytest.approx(2.2, abs=0.08)  # one or two frames at 25 fps


def test_recompressed_copy_reads_low(videos):
    """An honest re-shared copy must not look edited. Individual samples can read
    up to ~1.8 here where the synthetic pattern has fine moving detail (detail
    loses more to compression); the decision uses the level, not one sample."""
    result = _analyse(videos, "copy")
    assert result["mouth_level"] == "low"
    assert result["altered"] == []
    assert result["mouth_ratio_median"] < 1.0
    assert result["mouth_ratio_max"] < 3.0  # never reaches "high"


def test_mouth_edit_reads_high_only_where_it_happened(videos):
    result = _analyse(videos, "edited")
    assert result["mouth_level"] == "high"
    [span] = result["altered"]
    assert span["start"] == pytest.approx(1.0, abs=0.5)
    assert span["end"] == pytest.approx(3.0, abs=0.5)
    assert result["thresholds"]["status"] == "provisional"


def test_mouth_level_and_spans():
    assert mouth_level([]) == "unknown"
    assert mouth_level([1.0, 1.1, 0.9]) == "low"
    assert mouth_level([1.6, 1.7, 1.2]) == "medium"
    assert mouth_level([4.0, 5.0, 1.0]) == "high"
    assert altered_spans([(0.0, 1.0), (0.4, 4.0), (0.8, 5.0), (1.2, 1.0)], 0.4) == [
        {"start": 0.4, "end": 1.2}
    ]


def _transcript(text, start=0.0, step=0.5):
    words = [{"word": w, "start": start + i * step, "end": start + i * step + 0.4}
             for i, w in enumerate(text.split())]  # fmt: skip
    return {"segments": [{"words": words}]}


def test_compare_speech_shows_what_changed():
    original = _transcript("main aapko UPI ke baare mein bataungi", start=10.0)
    video = _transcript("main aapko ek special scheme ke baare mein bataungi")
    result = compare_speech(video, original, video_span=(0.0, 5.0), original_start=10.0)
    assert result["changes"] == [{"op": "replace", "original": "upi", "video": "ek special scheme"}]
    assert 0.5 < result["similarity"] < 1.0


def test_compare_speech_when_nothing_matches():
    original = _transcript("kal college mein workshop hai")
    video = _transcript("guaranteed returns teen mahine mein")
    assert compare_speech(video, original, video_span=(0, 5), original_start=0)["similarity"] < 0.3
