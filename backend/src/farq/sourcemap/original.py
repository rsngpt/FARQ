"""Find the original and show what changed.

For a part of the video whose picture matched a library clip:
1. Line the two up frame by frame (the source map's offset is only to the
   nearest half second).
2. Compare how much the mouth changed with how much the rest of the face
   changed. Re-compression changes a face about evenly; lip-sync concentrates
   change in the mouth.
3. Compare what was said in the original at that moment with what is said here.

Lower/upper face thresholds come from real measurements (25 Oct; median over
10 frame pairs): Roshan's genuine clips squeezed to 480p 1.04-1.09 (4 clips),
a plain stitch 1.06, a Wav2Lip GAN lip-sync of his face 1.41 (1.43 squeezed).
Small sample (4 genuine, 1 lip-sync in 2 encodings): re-check as more fakes are made.
Single frames are noisy (genuine frames reached 2.3), so levels use the median.
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

RATIO_MEDIUM = 1.15  # from real measurements; see module docstring
RATIO_HIGH = 1.25  # midpoint of the gap between genuine (<= 1.09) and lip-sync (>= 1.41)
SPAN_SMOOTHING = 3  # samples in the rolling median used to mark altered spans

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

# MediaPipe face-mesh landmark numbers.
# Lower face: nose base (2), lower cheeks (58, 288), jaw (172, 397), chin (152). Lip-sync
# tools such as Wav2Lip regenerate this whole area, not just the lips.
LOWER_FACE = [2, 58, 288, 172, 397, 152]
# Upper face: forehead (10), brows (54, 284), outer eye corners (33, 263), nose bridge
# between the eyes (6). Lip-sync leaves this untouched, so it is the reference.
UPPER_FACE = [10, 54, 284, 33, 263, 6]


class FaceFinder(Protocol):
    name: str
    version: str

    def regions(self, rgb: np.ndarray) -> tuple[Box, Box] | None:
        """(region a lip-sync would change, untouched reference region) for the
        main face, or None if there's no face."""
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
        # Lower vs upper face, not lips vs the rest: Wav2Lip regenerates the jaw and
        # chin too, which diluted a lips-only comparison (real lip-sync: 1.58x only).
        lower = _box(pts[LOWER_FACE], pad=0.05, size=(w, h))
        upper = _box(pts[UPPER_FACE], pad=0.05, size=(w, h))
        return lower, upper

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
    """low / medium / high from the median of the per-frame ratios."""
    if not ratios:
        return "unknown"
    median = float(np.median(ratios))
    if median >= RATIO_HIGH:
        return "high"
    if median >= RATIO_MEDIUM:
        return "medium"
    return "low"


def altered_spans(samples: list[tuple[float, float]], step: float) -> list[dict[str, float]]:
    """Runs of sampled times (video seconds, ratio) whose rolling median of
    SPAN_SMOOTHING samples is at or above RATIO_HIGH, so one noisy frame can't
    mark a span."""
    ratios = [r for _, r in samples]
    k = min(SPAN_SMOOTHING, len(ratios))
    # Always a full window (shifted inwards at the edges): a 2-value window at
    # the edge would let a single spike through.
    smoothed = [
        float(np.median(ratios[min(max(0, i - k // 2), len(ratios) - k) :][:k]))
        for i in range(len(ratios))
    ]
    spans: list[dict[str, float]] = []
    for (t, _), ratio in zip(samples, smoothed, strict=True):
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
