"""Voice-and-body check (layer 3). Real faces need the team's clips; these tests
check the maths on synthetic signals and the stage logic with stand-ins."""

from uuid import uuid4

import numpy as np
import pytest

from farq.binding import (
    calibrated,
    motion_from_landmarks,
    sync_score,
    visual_emphasis,
)
from farq.domain.casefile import Artifact, Strength, utcnow
from farq.pipeline.analyse import analyse
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import Stage, StageOutput
from farq.storage.tables import LibraryClipRow

RNG = np.random.default_rng(7)


def spikes(n: int, rng=RNG) -> np.ndarray:
    """An emphasis-like signal: mostly quiet with occasional bursts."""
    x = (rng.random(n) > 0.85).astype(float) * rng.random(n)
    return np.convolve(x, [0.3, 1.0, 0.3], mode="same")


def test_body_that_follows_the_voice_scores_higher_than_one_that_does_not():
    voice = spikes(400)  # 32 s at 12.5 per second
    follows = np.roll(voice, 2) + 0.2 * RNG.standard_normal(400)  # 160 ms behind, noisy
    unrelated = spikes(400, np.random.default_rng(99))
    together, apart = sync_score(voice, follows), sync_score(voice, unrelated)
    assert together > 0.6
    assert apart < 0.4
    assert together > apart + 0.3


def test_audio_emphasis_on_real_speech_length(tmp_path):
    """13 s of audio at 16 kHz (the length that broke pYIN in the container)."""
    import warnings

    from farq.binding import RATE, audio_emphasis

    t = np.arange(13 * 16000) / 16000
    # A voice-like tone whose pitch and loudness rise and fall every second.
    f = 150 + 40 * np.sin(2 * np.pi * 0.5 * t)
    y = (0.3 + 0.2 * np.sin(2 * np.pi * 1.0 * t)) * np.sin(2 * np.pi * np.cumsum(f) / 16000)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = audio_emphasis(y.astype(np.float32))
    assert abs(len(out) - 13 * RATE) <= 2
    assert np.isfinite(out).all() and out.std() > 0


def test_too_short_to_measure():
    assert sync_score(spikes(30), spikes(30)) is None  # under one 4 s window


def test_calibration_levels_and_wording():
    genuine = [0.55, 0.6, 0.5, 0.62, 0.58]
    assert calibrated(0.2, genuine) == ("high", "less in sync than all 5 of their real clips")
    assert calibrated(0.52, genuine) == ("medium", "less in sync than 4 of their 5 real clips")
    assert calibrated(0.6, genuine)[0] == "low"
    assert calibrated(0.1, [0.5, 0.6]) is None  # too few genuine clips to say anything


def test_visual_emphasis_fills_frames_without_a_face():
    motions = [(0.1, 0.2), None, (0.12, 0.22), (0.1, 0.25), None, (0.11, 0.2)]
    out = visual_emphasis(motions)
    assert len(out) == 6 and np.isfinite(out).all()
    assert visual_emphasis([None, None, None]).tolist() == [0.0, 0.0, 0.0]


def test_motion_is_scaled_by_face_size():
    pts = np.zeros((478, 2))
    pts[10], pts[152] = (100, 100), (100, 300)  # forehead, chin: face 200 px tall
    pts[33], pts[263], pts[1] = (80, 160), (120, 160), (100, 200)  # eyes, nose tip
    pts[105], pts[334], pts[159], pts[386] = (80, 140), (120, 140), (80, 155), (120, 155)
    nod, brow = motion_from_landmarks(pts)
    assert (nod, brow) == pytest.approx((40 / 200, 15 / 200))
    nod2, brow2 = motion_from_landmarks(pts * 2)  # same face, twice as close
    assert (nod2, brow2) == pytest.approx((nod, brow))


@pytest.fixture
def stitched_case(repo, rules, media, new_case, session, monkeypatch):
    """A case whose picture matched person 'enrolled-1', with audio, and a
    library holding that person's calibrated genuine clips."""

    def make(score: float, genuine: list[float]):
        for i, g in enumerate(genuine):
            session.add(LibraryClipRow(
                id=uuid4(), person="enrolled-1", title=f"g{i}", source="test", consent_note=None,
                media_key=f"library/{i}.mp4", sha256=f"{i:064d}", duration_s=30.0,
                fingerprints={"fps": 2.0, "frames": []}, transcript=None, phrases=None,
                binding_score=g, created_at=utcnow(),
            ))  # fmt: skip
        session.commit()
        monkeypatch.setattr("farq.pipeline.analyse.measure_clip", lambda *a, **k: score)
        media.objects["cases/x/audio16k.wav"] = b"RIFF"
        picture = {"start": 0.0, "end": 13.0, "clip_id": "c1", "person": "enrolled-1",
                   "title": "L1", "clip_start": 0.0}  # fmt: skip
        seed = Stage("seed", "cpu", lambda c, x: StageOutput(artifacts=[
            Artifact(stage="ingest", kind="fingerprints", data={"frames": []}),
            Artifact(stage="ingest", kind="audio_16k", storage_key="cases/x/audio16k.wav"),
            Artifact(stage="source_map", kind="source_map", data={"visual": [picture]}),
        ]))  # fmt: skip
        return run_pipeline(
            new_case(), repo, rules, media, [seed, Stage("analyse", "gpu", analyse)]
        )

    return make


def test_out_of_sync_voice_is_strong_evidence(stitched_case):
    case = stitched_case(0.1, [0.5, 0.55, 0.6, 0.52])
    [e] = case.evidence
    assert (e.type, e.strength, e.level) == ("voice_body_mismatch", Strength.STRONG, "high")
    assert "less in sync than all 4 of their real clips" in e.reason
    assert "score" not in e.details  # no raw numbers leave the stage
    assert case.artifact("binding").data["level"] == "high"


def test_normal_sync_adds_no_evidence(stitched_case):
    case = stitched_case(0.58, [0.5, 0.55, 0.6, 0.52])
    assert case.evidence == []
    assert case.artifact("binding").data["level"] == "low"


def test_without_enough_genuine_clips_there_is_no_reading(stitched_case):
    case = stitched_case(0.1, [0.5, 0.55])
    assert case.evidence == []
    assert case.artifact("binding").data["level"] == "unknown"
