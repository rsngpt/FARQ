from pathlib import Path

import pytest
from conftest import FakeAsrEngine, synthetic_video
from PIL import Image, ImageDraw

from farq.library import add_clip, load_clips
from farq.media import pdq
from farq.media.fingerprints import fingerprint_video
from farq.pipeline.ingest import ingest
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage


def _pattern(path: Path, seed: int) -> Path:
    """A busy synthetic frame (stripes and shapes), different for each seed."""
    img = Image.new("RGB", (640, 360), (20 + seed * 40 % 200, 60, 90))
    draw = ImageDraw.Draw(img)
    for i in range(12):
        x = (i * 53 + seed * 97) % 600
        draw.rectangle((x, 20 + i * 25, x + 40 + seed * 7 % 60, 40 + i * 25),
                       fill=((i * 40 + seed * 30) % 255, (i * 90) % 255, 200))  # fmt: skip
        draw.ellipse((300 + seed * 11 % 200, 100, 380, 200 + i), outline="white", width=3)
    img.save(path, quality=95)
    return path


def _distance(a: Path, b: Path) -> int:
    ha, _ = pdq.hash_image(a)
    hb, _ = pdq.hash_image(b)
    return int(pdq.distances(pdq.to_bits([ha]), pdq.to_bits([hb]))[0, 0])


def test_recompressed_and_resized_frame_still_matches(tmp_path):
    original = _pattern(tmp_path / "a.jpg", seed=1)
    with Image.open(original) as img:
        img.resize((320, 180)).save(tmp_path / "small.jpg", quality=25)
    assert _distance(original, tmp_path / "small.jpg") <= pdq.MATCH_DISTANCE


def test_frame_with_a_mouth_sized_edit_still_matches(tmp_path):
    """The source map relies on this: lip-sync changes a small region, so the
    altered frame must still match its original."""
    original = _pattern(tmp_path / "a.jpg", seed=2)
    with Image.open(original) as img:
        draw = ImageDraw.Draw(img)
        draw.rectangle((290, 230, 350, 260), fill=(180, 60, 60))  # ~1% of the frame
        img.save(tmp_path / "mouth.jpg", quality=80)
    assert _distance(original, tmp_path / "mouth.jpg") <= pdq.MATCH_DISTANCE


def test_different_pictures_do_not_match(tmp_path):
    a = _pattern(tmp_path / "a.jpg", seed=1)
    b = _pattern(tmp_path / "b.jpg", seed=4)
    assert _distance(a, b) > pdq.MATCH_DISTANCE


def test_video_fingerprints_at_two_per_second(tmp_path):
    video = tmp_path / "v.mp4"
    synthetic_video(video, seconds=5)
    work = tmp_path / "work"
    work.mkdir()
    fp = fingerprint_video(video, work, 5.0)
    assert fp["fps"] == 2.0
    assert [f["t"] for f in fp["frames"]] == pytest.approx([i / 2 for i in range(10)], abs=0.06)
    assert all(len(f["pdq"]) == 64 for f in fp["frames"])


def test_ingest_stores_fingerprints(repo, rules, media, new_case, sample_video):
    case = run_pipeline(
        new_case(sample_video), repo, rules, media, [Stage("ingest", "cpu", ingest)]
    )
    fp = case.artifact("fingerprints")
    assert len(fp.data["frames"]) == 6  # 3 s at 2 per second
    assert fp.model_name == "pdqhash"


def test_library_add_stores_clip_once(session, media, tmp_path):
    clip = tmp_path / "lib-01-intro.mp4"
    synthetic_video(clip, seconds=3)
    asr = FakeAsrEngine()
    asr.result = asr.result | {"text": "namaste main enrolled hoon"}

    details = {"person": "enrolled-1", "title": "intro", "source": "team recording",
               "consent_note": "test"}  # fmt: skip
    clip_id, existed = add_clip(session, media, asr, clip, **details)
    again, existed_again = add_clip(session, media, asr, clip, **details)

    assert (existed, existed_again, again) == (False, True, clip_id)
    [stored] = load_clips(session)
    assert stored.person == "enrolled-1"
    assert len(stored.fingerprints["frames"]) == 6
    assert stored.transcript["text"] == "namaste main enrolled hoon"
    assert stored.transcript["model"] == "fake-asr test"
    assert f"library/{clip_id}/original.mp4" in media.objects
    assert len(asr.files_heard) == 1  # the second add did no work
