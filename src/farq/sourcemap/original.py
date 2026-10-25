"""Find the original and show what changed.

For a part of the video whose picture matched a library clip:
1. Line the two up frame by frame (the source map's offset is only to the
   nearest half second).
2. Compare how much the mouth changed with how much the rest of the face
   changed. Re-compression changes a face about evenly; lip-sync concentrates
   change in the mouth.
3. Compare what was said in the original at that moment with what is said here.

Mouth/face ratio thresholds are PROVISIONAL: from one public-domain test photo
(re-compressed only: 1.01-1.13; mouth re-drawn: 4.9-35.4). Re-calibrate on the
team's genuine clips before relying on them.
"""

import hashlib
import urllib.request
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from PIL import Image, ImageFilter

from farq.sourcemap.speech import words_of

Box = tuple[int, int, int, int]  # left, top, right, bottom in pixels

QUERY_FPS = 5  # frames per second sampled from the forwarded video
ORIGINAL_FPS = 25  # from the original, so a match can land on any frame
SEARCH_FRAMES = 12  # +/- frames of the original searched around the expected one
MAX_SPAN_S = 20.0  # longest stretch compared per segment
FACE_SAMPLES = 10  # frame pairs checked for mouth vs face

RATIO_MEDIUM = 1.5  # provisional; see module docstring
RATIO_HIGH = 3.0

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

# MediaPipe face-mesh landmark numbers for the outer lips and the face outline.
LIPS = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185]
FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400,
             377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103,
             67, 109]  # fmt: skip


class FaceFinder(Protocol):
    name: str
    version: str

    def regions(self, rgb: np.ndarray) -> tuple[Box, Box] | None:
        """(mouth box, face box) for the main face, or None if there's no face."""
        ...


class MediaPipeFaceFinder:
    name = "MediaPipe Face Landmarker"

    def __init__(self, model_path: Path):
        if not model_path.exists():
            model_path.parent.mkdir(parents=True, exist_ok=True)
            model_path.write_bytes(urllib.request.urlopen(FACE_MODEL_URL, timeout=60).read())
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if digest != FACE_MODEL_SHA256:
            raise ValueError(f"{model_path} is not the expected face model (sha256 {digest})")
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        self._mp = mp
        self.version = f"face_landmarker {digest[:12]} mediapipe {mp.__version__}"
        self._landmarker = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)), num_faces=1
            )
        )

    def _landmarks(self, rgb: np.ndarray) -> np.ndarray | None:
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb)
        )
        result = self._landmarker.detect(image)
        if not result.face_landmarks:
            return None
        h, w = rgb.shape[:2]
        return np.array([(p.x * w, p.y * h) for p in result.face_landmarks[0]])

    def regions(self, rgb: np.ndarray) -> tuple[Box, Box] | None:
        pts = self._landmarks(rgb)
        if pts is None:
            return None
        h, w = rgb.shape[:2]
        return _box(pts[LIPS], pad=0.25, size=(w, h)), _box(pts[FACE_OVAL], pad=0.0, size=(w, h))

    def motion(self, rgb: np.ndarray) -> tuple[float, float] | None:
        """Head nod and eyebrow height for the voice-and-body check."""
        from farq.binding import motion_from_landmarks

        pts = self._landmarks(rgb)
        return None if pts is None else motion_from_landmarks(pts)


@lru_cache
def get_face_finder(model_path: Path) -> FaceFinder:
    return MediaPipeFaceFinder(model_path)


def _box(points: np.ndarray, *, pad: float, size: tuple[int, int]) -> Box:
    x0, y0 = points.min(axis=0)
    x1, y1 = points.max(axis=0)
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    w, h = size
    return (max(0, int(x0 - px)), max(0, int(y0 - py)), min(w, int(x1 + px)), min(h, int(y1 + py)))


def _gray_small(rgb: np.ndarray) -> np.ndarray:
    return np.asarray(Image.fromarray(rgb).convert("L").resize((64, 36)), dtype=np.float32)


def align(query: np.ndarray, original: np.ndarray, *, lead_in_s: float) -> float:
    """Fine offset correction in seconds. `query` frames are at QUERY_FPS from the
    segment start; `original` frames at ORIGINAL_FPS from `lead_in_s` before the
    matching moment in the original."""
    q_small = [_gray_small(f) for f in query]
    o_small = [_gray_small(f) for f in original]
    shifts = []
    for i, q in enumerate(q_small):
        expected = round((i / QUERY_FPS + lead_in_s) * ORIGINAL_FPS)
        window = range(max(0, expected - SEARCH_FRAMES),
                       min(len(o_small), expected + SEARCH_FRAMES + 1))  # fmt: skip
        if not window:
            continue
        best = min(window, key=lambda k: float(np.abs(q - o_small[k]).mean()))
        shifts.append(best - expected)
    return float(np.median(shifts)) / ORIGINAL_FPS if shifts else 0.0


def change_ratio(original: np.ndarray, query: np.ndarray, mouth: Box, face: Box) -> float:
    """How much more the mouth changed than the rest of the face (1.0 = evenly)."""

    def gray(rgb: np.ndarray) -> np.ndarray:
        img = Image.fromarray(rgb).convert("L").filter(ImageFilter.GaussianBlur(1))
        return np.asarray(img, dtype=np.float32)

    diff = np.abs(gray(original) - gray(query))
    in_mouth = np.zeros(diff.shape, dtype=bool)
    in_mouth[mouth[1] : mouth[3], mouth[0] : mouth[2]] = True
    in_face = np.zeros(diff.shape, dtype=bool)
    in_face[face[1] : face[3], face[0] : face[2]] = True
    in_face &= ~in_mouth
    if not in_mouth.any() or not in_face.any():
        return 1.0
    return float(diff[in_mouth].mean() / max(diff[in_face].mean(), 1e-3))


def mouth_level(ratios: list[float]) -> str:
    """low / medium / high from per-frame ratios (provisional thresholds)."""
    if not ratios:
        return "unknown"
    high_share = sum(r >= RATIO_HIGH for r in ratios) / len(ratios)
    if high_share >= 0.3:
        return "high"
    if float(np.median(ratios)) >= RATIO_MEDIUM or high_share > 0:
        return "medium"
    return "low"


def altered_spans(samples: list[tuple[float, float]], step: float) -> list[dict[str, float]]:
    """Runs of sampled times (video seconds, ratio) at or above RATIO_HIGH."""
    spans: list[dict[str, float]] = []
    for t, ratio in samples:
        if ratio < RATIO_HIGH:
            continue
        if spans and t - spans[-1]["end"] <= step + 1e-6:
            spans[-1]["end"] = t + step
        else:
            spans.append({"start": t, "end": t + step})
    return [{k: round(v, 2) for k, v in s.items()} for s in spans]


def compare_speech(
    video_transcript: dict[str, Any] | None,
    original_transcript: dict[str, Any] | None,
    *,
    video_span: tuple[float, float],
    original_start: float,
) -> dict[str, Any] | None:
    """What the original said at this moment vs what this video says."""
    start, end = video_span
    said = [w["w"] for w in words_of(video_transcript) if start <= w["start"] < end]
    orig_end = original_start + (end - start)
    original = [w["w"] for w in words_of(original_transcript)
                if original_start <= w["start"] < orig_end]  # fmt: skip
    if not said and not original:
        return None
    matcher = SequenceMatcher(None, original, said, autojunk=False)
    changes = [
        {"op": op, "original": " ".join(original[i1:i2]), "video": " ".join(said[j1:j2])}
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
        if op != "equal"
    ]
    return {
        "similarity": round(matcher.ratio(), 3),
        "original_text": " ".join(original)[:300],
        "video_text": " ".join(said)[:300],
        "changes": changes[:5],
    }


PAIR_SEARCH_FRAMES = 3  # +/- original frames tried for each pair


def _best_frame(query: np.ndarray, original: np.ndarray, k: int, mouth: Box, face: Box) -> int:
    """The original frame near k that best matches the query on the face minus the mouth."""

    def face_only(rgb: np.ndarray) -> np.ndarray:
        g = np.asarray(Image.fromarray(rgb).convert("L"), dtype=np.float32)[
            face[1] : face[3], face[0] : face[2]
        ].copy()
        g[mouth[1] - face[1] : mouth[3] - face[1], mouth[0] - face[0] : mouth[2] - face[0]] = 0
        return g

    q = face_only(query)
    candidates = range(
        max(0, k - PAIR_SEARCH_FRAMES), min(len(original), k + PAIR_SEARCH_FRAMES + 1)
    )
    return min(candidates, key=lambda c: float(np.abs(face_only(original[c]) - q).mean()))


def analyse_segment(
    segment: dict[str, Any],
    query_frames: np.ndarray,
    original_frames: np.ndarray,
    finder: FaceFinder,
    *,
    lead_in_s: float,
) -> dict[str, Any]:
    """Align, then measure mouth vs face over up to FACE_SAMPLES frame pairs."""
    shift = align(query_frames, original_frames, lead_in_s=lead_in_s)
    step = 1 / QUERY_FPS
    picks = np.linspace(0, len(query_frames) - 1, num=min(FACE_SAMPLES, len(query_frames)))
    samples: list[tuple[float, float]] = []
    faces_found = 0
    for i in sorted({int(round(p)) for p in picks}):
        k = round((i / QUERY_FPS + lead_in_s + shift) * ORIGINAL_FPS)
        if not 0 <= k < len(original_frames):
            continue
        regions = finder.regions(original_frames[k])
        if regions is None:
            continue
        faces_found += 1
        # Re-align this pair on the face *without* the mouth: the mouth moves
        # most when someone talks, so even one frame of misalignment would make
        # an honest copy's mouth look edited.
        k = _best_frame(query_frames[i], original_frames, k, *regions)
        ratio = change_ratio(original_frames[k], query_frames[i], *regions)
        samples.append((segment["start"] + i * step, round(ratio, 2)))
    ratios = [r for _, r in samples]
    span_step = (len(query_frames) / QUERY_FPS) / max(len(samples), 1)
    return {
        "offset_s": round(segment["clip_start"] - segment["start"] + shift, 2),
        "frames_compared": len(samples),
        "faces_found": faces_found,
        "mouth_ratio_median": round(float(np.median(ratios)), 2) if ratios else None,
        "mouth_ratio_max": round(max(ratios), 2) if ratios else None,
        "mouth_level": mouth_level(ratios),
        "altered": altered_spans(samples, span_step),
        "samples": samples,
        "thresholds": {"medium": RATIO_MEDIUM, "high": RATIO_HIGH, "status": "provisional"},
        "face_model": f"{finder.name} {finder.version}",
        "face_model_version": finder.version,
    }
