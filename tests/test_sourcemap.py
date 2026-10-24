"""Visual source map on synthetic library clips and a stitched fake made the
way the demo fakes will be: picture cut from two clips, then shrunk and
heavily re-compressed (as WhatsApp does)."""

from pathlib import Path

import pytest
from conftest import FakeAsrEngine, ffmpeg_make

from farq.library import add_clip, load_clips
from farq.media.fingerprints import fingerprint_video
from farq.sourcemap.visual import visual_map

# Three visually different synthetic "speeches", 8 s each, changing over time.
SOURCES = {
    "clip-a": "testsrc2=duration=8:size=640x360:rate=25",
    "clip-b": "mandelbrot=size=640x360:rate=25",
    "clip-c": "life=size=640x360:rate=25:seed=7:mold=10",
}


@pytest.fixture(scope="module")
def media_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("sourcemap")
    for name, source in SOURCES.items():
        ffmpeg_make(
            d / f"{name}.mp4", "-f", "lavfi", "-i", source, "-t", "8", "-pix_fmt", "yuv420p"
        )
    # Stitched fake: clip-a 2-5 s, then clip-b 1-4 s; small and heavily compressed.
    ffmpeg_make(
        d / "fake.mp4",
        "-i", str(d / "clip-a.mp4"), "-i", str(d / "clip-b.mp4"),
        "-filter_complex",
        "[0:v]trim=2:5,setpts=PTS-STARTPTS[a];[1:v]trim=1:4,setpts=PTS-STARTPTS[b];"
        "[a][b]concat=n=2:v=1:a=0,scale=320:180[v]",
        "-map", "[v]", "-c:v", "libx264", "-crf", "35",
    )  # fmt: skip
    return d


@pytest.fixture
def library(session, media, media_dir):
    """Clips a and b are in the library; clip-c is not."""
    for name in ("clip-a", "clip-b"):
        add_clip(session, media, FakeAsrEngine(), media_dir / f"{name}.mp4",
                 person="enrolled-1", title=name, source="test", consent_note=None)  # fmt: skip
    return load_clips(session)


def _frames(path: Path, tmp_path: Path) -> list[dict]:
    work = tmp_path / path.stem
    work.mkdir()
    return fingerprint_video(path, work, None)["frames"]


def test_stitched_fake_maps_to_both_sources(library, media_dir, tmp_path):
    timeline = visual_map(_frames(media_dir / "fake.mp4", tmp_path), library)
    matched = [s for s in timeline if s["clip_id"]]
    assert [s["title"] for s in matched] == ["clip-a", "clip-b"]
    a, b = matched
    assert a["start"] == pytest.approx(0, abs=0.6) and a["end"] == pytest.approx(3, abs=0.6)
    assert a["clip_start"] == pytest.approx(2, abs=0.6)  # cut from clip-a at 2 s
    assert b["start"] == pytest.approx(3, abs=0.6) and b["end"] == pytest.approx(6, abs=0.6)
    assert b["clip_start"] == pytest.approx(1, abs=0.6)  # cut from clip-b at 1 s
    assert all(s["mean_distance"] <= 31 for s in matched)


def test_footage_not_in_library_has_no_source(library, media_dir, tmp_path):
    timeline = visual_map(_frames(media_dir / "clip-c.mp4", tmp_path), library)
    assert [s["clip_id"] for s in timeline] == [None]
    assert timeline[0]["start"] == 0 and timeline[0]["end"] == pytest.approx(8, abs=0.6)


def test_pipeline_stage_stores_the_source_map(library, repo, rules, media, new_case, media_dir):
    from farq.pipeline.ingest import ingest
    from farq.pipeline.runner import run_pipeline
    from farq.pipeline.source_map import source_map
    from farq.pipeline.stages import Stage

    stages = [Stage("ingest", "cpu", ingest), Stage("source_map", "cpu", source_map)]
    case = run_pipeline(new_case((media_dir / "fake.mp4").read_bytes()), repo, rules, media, stages)
    data = case.artifact("source_map").data
    assert data["library_clips"] == 2
    assert [s.get("title") for s in data["visual"]] == ["clip-a", "clip-b"]
    # Each picture match was lined up with its original: the fake was cut from
    # clip-a at 2 s and clip-b at 1 s.
    offsets = {o["segment"]["title"]: o["offset_s"] for o in data["originals"]}
    assert offsets["clip-a"] == pytest.approx(2.0, abs=0.12)
    # offset = library time - video time: clip-b's 1 s plays at 3 s in the fake.
    assert offsets["clip-b"] == pytest.approx(1.0 - 3.0, abs=0.12)
    # No face in synthetic patterns (stand-in finder): no mouth reading, no evidence.
    assert {o["mouth_level"] for o in data["originals"]} == {"unknown"}
    assert case.evidence == []


def test_empty_library_or_video(media_dir, tmp_path):
    frames = _frames(media_dir / "clip-a.mp4", tmp_path)
    assert [s["clip_id"] for s in visual_map(frames, [])] == [None]
    assert visual_map([], []) == []
