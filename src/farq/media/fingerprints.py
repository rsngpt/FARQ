"""Frame fingerprints for source matching, made the same way for forwarded
videos (ingest) and for library clips, so the two can be compared."""

from pathlib import Path
from typing import Any

from farq.media import ffmpeg, pdq
from farq.settings import get_settings


def fingerprint_video(path: Path, workdir: Path, duration_s: float | None) -> dict[str, Any]:
    """PDQ hash of frames at FINGERPRINT_FPS (fewer for long videos).
    Returns {"fps": ..., "frames": [{"t": seconds, "pdq": hex, "q": quality}]}."""
    settings = get_settings()
    if duration_s is None:
        # Without the length, frame thinning would assume the 10-minute maximum
        # and sample short videos too sparsely.
        duration_s = ffmpeg.probe(path, settings.ffmpeg_timeout_s).duration_s
    out = workdir / "fingerprint-frames"
    out.mkdir()
    fps, frames = ffmpeg.extract_frames(
        path,
        out,
        duration_s=duration_s,
        max_frames=settings.max_fingerprint_frames,
        max_seconds=settings.max_media_seconds,
        timeout=settings.ffmpeg_timeout_s,
        target_fps=settings.fingerprint_fps,
    )
    hashed = []
    for t, frame in frames:
        digest, quality = pdq.hash_image(frame)
        hashed.append({"t": round(t, 3), "pdq": digest, "q": quality})
        frame.unlink()  # hashed; the image itself isn't needed
    return {"fps": fps, "frames": hashed}
