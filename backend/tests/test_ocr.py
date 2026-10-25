from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from farq.ocr.engine import TextLine
from farq.pipeline.ingest import ingest
from farq.pipeline.ocr import merge_lines, ocr, spread
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage
from farq.settings import get_settings
from farq.text import normalise

BOX = [[0, 0], [10, 0], [10, 10], [0, 10]]
INGEST_AND_OCR = [Stage("ingest", "cpu", ingest), Stage("ocr", "cpu", ocr)]


def line(text: str, score: float = 0.95) -> TextLine:
    return TextLine(text=text, score=score, box=BOX)


def test_spread_picks_evenly_including_the_first():
    picked = spread(list(range(30)), 12)
    assert len(picked) == 12
    assert picked[0] == 0
    assert all(b - a in (2, 3) for a, b in zip(picked, picked[1:], strict=False))
    assert spread([1, 2, 3], 12) == [1, 2, 3]


def test_same_overlay_across_frames_becomes_one_line():
    lines = merge_lines(
        [
            (0.0, [line("Guaranteed 40% returns")]),
            (5.0, [line("Guaranteed 40% retums", 0.80)]),  # misread, same overlay
            (10.0, [line("Guaranteed 40% returns", 0.99)]),
        ],
        min_score=0.6,
    )
    assert len(lines) == 1
    assert lines[0]["text"] == "Guaranteed 40% returns"
    assert (lines[0]["first_t"], lines[0]["last_t"], lines[0]["frames"]) == (0.0, 10.0, 3)
    assert lines[0]["score"] == 0.99  # clearest reading kept


def test_different_text_stays_separate_and_ordered_by_first_seen():
    lines = merge_lines(
        [(4.0, [line("Join WhatsApp group")]), (0.0, [line("Call 98765 43210")])],
        min_score=0.6,
    )
    assert [m["text"] for m in lines] == ["Call 98765 43210", "Join WhatsApp group"]


def test_low_confidence_and_single_characters_are_dropped():
    lines = merge_lines(
        [(0.0, [line("0", 0.99), line("blurry", 0.3), line("OK text")])], min_score=0.6
    )
    assert [m["text"] for m in lines] == ["OK text"]


def test_devanagari_digits_become_ascii():
    assert normalise("गारंटीड ४0% रिटर्न ३ महीने") == "गारंटीड 40% रिटर्न 3 महीने"


def test_stage_reads_at_most_the_configured_frames(
    repo, rules, media, new_case, fake_ocr, set_setting, tmp_path
):
    from conftest import synthetic_video

    set_setting("OCR_MAX_FRAMES", "4")
    fake_ocr.lines_for = lambda i: [line("UPI: farqdemo@okfakebank")] if i == 1 else []
    video = synthetic_video(tmp_path / "ten.mp4", seconds=10)
    case = run_pipeline(new_case(video), repo, rules, media, INGEST_AND_OCR)

    assert len(fake_ocr.images_read) == 4
    data = case.artifact("ocr").data
    assert (data["frames_read"], data["frames_available"]) == (4, 10)
    [found] = data["lines"]
    assert found["text"] == "UPI: farqdemo@okfakebank"
    assert found["first_t"] == pytest.approx(2.0, abs=0.2)  # frame index 1 of 0,2,5,7 s
    assert case.artifact("ocr").model_name == "fake-ocr"


def test_voice_note_has_nothing_to_read(repo, rules, media, new_case, fake_ocr, tmp_path):
    from conftest import ffmpeg_make

    voice = ffmpeg_make(
        tmp_path / "v.ogg", "-f", "lavfi", "-i", "sine=duration=2", "-c:a", "libopus"
    )
    case = run_pipeline(new_case(voice, ".ogg"), repo, rules, media, INGEST_AND_OCR)
    assert case.artifact("ocr") is None
    assert fake_ocr.images_read == []


def _draw_frame(path: Path, lines: list[tuple[str, ImageFont.ImageFont]]) -> None:
    img = Image.new("RGB", (1280, 720), (40, 60, 90))
    draw = ImageDraw.Draw(img)
    y = 520
    for text, font in lines:
        draw.rectangle((40, y - 6, 1240, y + 56), fill=(200, 20, 20))
        draw.text((60, y), text, font=font, fill="white")
        y += 80
    img.save(path, quality=90)


@pytest.mark.real_models
def test_real_ocr_reads_a_scam_style_overlay(tmp_path):
    from farq.ocr.engine import PaddleOcrEngine

    font = ImageFont.load_default(size=44)
    frame = tmp_path / "frame.jpg"
    _draw_frame(frame, [("Call 98765 43210 UPI: farqdemo@okfakebank", font),
                        ("Guaranteed 40% returns in 3 months", font)])  # fmt: skip
    [lines] = PaddleOcrEngine(get_settings().ocr_det_side).read([frame])
    text = " ".join(normalise(t.text) for t in lines)
    assert "98765 43210" in text
    assert "farqdemo@okfakebank" in text
    assert "40% returns" in text
