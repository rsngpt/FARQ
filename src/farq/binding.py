"""Voice-and-body check (layer 3): do this voice and this body belong together?

In genuine speech, head nods and eyebrow raises tend to come with vocal
emphasis (pitch and loudness rises). In a stitched fake, the voice came from
another recording, so the body still moves to the original words. The mouth is
ignored: it is the part a lip-sync tool forges to match.

First version: no training. A sync score is compared with the same person's
genuine library clips; we only say "less in sync than N of their real clips"
when there are at least MIN_CALIBRATION clips. Not yet validated on real faces
(the team's clips are needed).
"""

import warnings
from pathlib import Path
from typing import Protocol

import numpy as np

RATE = 12.5  # samples per second for both signals
WINDOW_S = 4.0
HOP_S = 2.0
MAX_LAG_S = 0.32  # voice and body may be up to this far apart
MIN_CALIBRATION = 3  # genuine clips needed before we give a level
MAX_SECONDS = 30.0

# MediaPipe face-mesh landmarks
NOSE_TIP, LEFT_EYE, RIGHT_EYE = 1, 33, 263
FOREHEAD, CHIN = 10, 152
BROWS, LIDS = (105, 334), (159, 386)


class FaceMotion(Protocol):
    def motion(self, rgb: np.ndarray) -> tuple[float, float] | None:
        """(head nod position, eyebrow height), both scaled by face height, or None."""
        ...


def motion_from_landmarks(pts: np.ndarray) -> tuple[float, float]:
    """pts: (478, 2) landmark pixel positions."""
    face_h = max(float(np.linalg.norm(pts[CHIN] - pts[FOREHEAD])), 1e-6)
    eyes_y = (pts[LEFT_EYE, 1] + pts[RIGHT_EYE, 1]) / 2
    nod = (pts[NOSE_TIP, 1] - eyes_y) / face_h
    brow = float(np.mean([pts[LIDS[i], 1] - pts[BROWS[i], 1] for i in range(2)])) / face_h
    return float(nod), brow


def _z(x: np.ndarray) -> np.ndarray:
    x = np.nan_to_num(np.asarray(x, dtype=np.float64))
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-9 else np.zeros_like(x)


def _smooth(x: np.ndarray, n: int = 3) -> np.ndarray:
    return np.convolve(x, np.ones(n) / n, mode="same") if len(x) >= n else x


def visual_emphasis(motions: list[tuple[float, float] | None]) -> np.ndarray:
    """How fast head and eyebrows move, per sample (gaps filled from neighbours)."""
    arr = np.array([m if m is not None else (np.nan, np.nan) for m in motions], dtype=np.float64)
    if len(arr) == 0:
        return np.zeros(0)
    for col in range(2):  # fill frames where no face was found
        series = arr[:, col]
        ok = ~np.isnan(series)
        if ok.sum() < 2:
            return np.zeros(len(arr))
        arr[:, col] = np.interp(np.arange(len(series)), np.flatnonzero(ok), series[ok])
    speed = np.abs(np.diff(arr, axis=0, prepend=arr[:1]))
    return _smooth(_z(speed[:, 0]) + _z(speed[:, 1]))


AUDIO_STEP = 4  # pitch frames (20 ms each) per signal sample (80 ms)


def audio_emphasis(samples: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Pitch rises plus loudness rises, per sample.

    Pitch from librosa's YIN at 20 ms steps, averaged to RATE. (pYIN broke at
    80 ms steps, "Target size must be at least input size", and took ~17 s.)
    Frames quieter than half the median loudness count as unvoiced."""
    import librosa

    hop = int(sr / RATE / AUDIO_STEP)
    f0 = librosa.yin(samples, fmin=70, fmax=400, sr=sr, frame_length=1024, hop_length=hop)
    rms = librosa.feature.rms(y=samples, frame_length=1024, hop_length=hop)[0]
    n = min(len(f0), len(rms)) // AUDIO_STEP * AUDIO_STEP
    if n == 0:
        return np.zeros(0)
    f0, rms = f0[:n], rms[:n]
    voiced = rms > 0.5 * np.median(rms)
    semitones = np.where(voiced, 12 * np.log2(f0 / 100.0), np.nan)
    with warnings.catch_warnings():  # "Mean of empty slice" where all 4 frames are unvoiced
        warnings.simplefilter("ignore", RuntimeWarning)
        pitch = np.nanmean(semitones.reshape(-1, AUDIO_STEP), axis=1)  # NaN where unvoiced
    loud = np.log(rms.reshape(-1, AUDIO_STEP).mean(axis=1) + 1e-6)
    pitch_rise = np.clip(np.nan_to_num(np.diff(pitch, prepend=np.nan)), 0, None)
    loud_rise = np.clip(np.diff(loud, prepend=loud[:1]), 0, None)
    return _smooth(_z(pitch_rise) + _z(loud_rise))


def sync_score(voice: np.ndarray, body: np.ndarray) -> float | None:
    """Median over 4 s windows of the best correlation within +/-320 ms."""
    n = min(len(voice), len(body))
    win, hop, max_lag = int(WINDOW_S * RATE), int(HOP_S * RATE), int(MAX_LAG_S * RATE)
    if n < win:
        return None
    best = []
    for start in range(0, n - win + 1, hop):
        a = voice[start : start + win]
        corrs = []
        for lag in range(-max_lag, max_lag + 1):
            lo, hi = start + lag, start + lag + win
            if lo < 0 or hi > n:
                continue
            b = body[lo:hi]
            if a.std() > 1e-9 and b.std() > 1e-9:
                corrs.append(float(np.corrcoef(a, b)[0, 1]))
        if corrs:
            best.append(max(corrs))
    return round(float(np.median(best)), 3) if best else None


def calibrated(score: float, genuine: list[float]) -> tuple[str, str] | None:
    """(level, explanation) against the person's genuine clips, or None if there
    are too few to say anything. Lower score = less in sync."""
    if len(genuine) < MIN_CALIBRATION:
        return None
    n = len(genuine)
    more_in_sync = sum(g > score for g in genuine)
    if more_in_sync == n:
        return "high", f"less in sync than all {n} of their real clips"
    if more_in_sync / n >= 0.8:
        return "medium", f"less in sync than {more_in_sync} of their {n} real clips"
    return "low", f"as in sync as their real clips ({n - more_in_sync} of {n} are no better)"


def measure_clip(video: Path, wav: Path, motion: FaceMotion, *, timeout: float) -> float | None:
    """Sync score for a video file and its 16 kHz audio (first MAX_SECONDS)."""
    from farq.asr.engine import read_wav_16k
    from farq.media import ffmpeg

    frames = ffmpeg.read_frames(video, start=0, duration=MAX_SECONDS, fps=RATE,
                                size=(640, 360), timeout=timeout)  # fmt: skip
    body = visual_emphasis([motion.motion(f) for f in frames])
    voice = audio_emphasis(read_wav_16k(wav)[: int(MAX_SECONDS * 16000)])
    return sync_score(voice, body)
