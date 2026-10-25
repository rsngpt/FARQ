"""Guarded ffprobe / ffmpeg calls for files strangers send us.

Every call reads only local files (no network or other protocols), accepts only
common media formats (no playlists or concat lists, which can point FFmpeg at
other files on the server), and has a time limit.
"""

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

# Demuxers we accept. "mov" covers mp4/m4a/3gp, "matroska" covers webm.
ALLOWED_FORMATS = "mov,matroska,ogg,mp3,wav,aac,image2,jpeg_pipe,png_pipe,webp_pipe"
INPUT_GUARDS = ["-protocol_whitelist", "file", "-format_whitelist", ALLOWED_FORMATS]

# Container tags worth keeping. Others (GPS location, device owner) are dropped.
KEPT_TAGS = {"creation_time", "encoder", "major_brand", "compatible_brands"}

IMAGE_FORMATS = {"image2", "jpeg_pipe", "png_pipe", "webp_pipe"}


class MediaError(Exception):
    """The file can't be read as video, audio or an image."""


@dataclass
class MediaInfo:
    kind: str  # "video", "audio" or "image"
    container: str
    duration_s: float | None
    video: dict[str, Any] | None = None
    audio: dict[str, Any] | None = None
    tags: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{args[0]} took longer than {timeout:.0f} s") from exc
    except subprocess.CalledProcessError as exc:
        last = (exc.stderr or "").strip().splitlines()[-1:] or ["no details"]
        raise MediaError(f"{args[0]} could not read the file: {last[0]}") from exc


@lru_cache
def version() -> str:
    first = _run(["ffmpeg", "-version"], timeout=10).stdout.splitlines()[0]
    match = re.search(r"version (\S+)", first)
    return match.group(1) if match else "unknown"


def probe(path: Path, timeout: float) -> MediaInfo:
    out = _run(
        ["ffprobe", "-v", "error", *INPUT_GUARDS, "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        timeout,
    )  # fmt: skip
    return _summarise(json.loads(out.stdout))


def _summarise(data: dict[str, Any]) -> MediaInfo:
    fmt = data.get("format", {})
    container = fmt.get("format_name", "")
    streams = data.get("streams", [])
    # Cover art inside audio files shows up as a video stream; ignore it.
    video = next(
        (s for s in streams
         if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")),
        None,
    )  # fmt: skip
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if video is not None and container in IMAGE_FORMATS:
        kind = "image"
    elif video is not None:
        kind = "video"
    elif audio is not None:
        kind = "audio"
    else:
        raise MediaError("no video, audio or image found in the file")

    duration = fmt.get("duration")
    return MediaInfo(
        kind=kind,
        container=container,
        duration_s=float(duration) if duration and kind != "image" else None,
        video=None
        if video is None
        else {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": _rate(video.get("avg_frame_rate")),
        },
        audio=None
        if audio is None
        else {
            "codec": audio.get("codec_name"),
            "sample_rate": int(audio.get("sample_rate", 0)) or None,
            "channels": audio.get("channels"),
        },
        tags={k: str(v) for k, v in fmt.get("tags", {}).items() if k.lower() in KEPT_TAGS},
    )


def _rate(value: str | None) -> float | None:
    if not value or "/" not in value:
        return None
    num, den = value.split("/")
    return round(int(num) / int(den), 3) if int(den) else None


_PTS_TIME = re.compile(r"Parsed_showinfo.*?pts_time:\s*([0-9.]+)")


def extract_frames(
    path: Path,
    out_dir: Path,
    *,
    duration_s: float | None,
    max_frames: int,
    max_seconds: float,
    timeout: float,
    target_fps: float = 1.0,
) -> tuple[float, list[tuple[float, Path]]]:
    """target_fps frames per second, or fewer for long videos so at most
    max_frames come out, spread evenly. Returns (fps used, [(timestamp_s, jpg)])."""
    span = min(duration_s or max_seconds, max_seconds)
    fps = target_fps if span * target_fps <= max_frames else max_frames / span
    out = _run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info", *INPUT_GUARDS,
         "-i", str(path), "-t", str(max_seconds),
         "-vf", f"fps={fps:.6f},scale='min(1280,iw)':-2,showinfo",
         "-frames:v", str(max_frames), "-q:v", "3", str(out_dir / "%05d.jpg")],
        timeout,
    )  # fmt: skip
    times = [float(t) for t in _PTS_TIME.findall(out.stderr)]
    files = sorted(out_dir.glob("*.jpg"))
    if not files:
        raise MediaError("no frames could be extracted")
    # Frames are written in the order showinfo logs them, but at a time or frame
    # limit the filter can log one more frame than gets written; it is always last.
    if len(times) < len(files):
        raise MediaError(f"frame timestamps ({len(times)}) don't match frames ({len(files)})")
    return fps, list(zip(times[: len(files)], files, strict=True))


def read_frames(
    path: Path,
    *,
    start: float,
    duration: float,
    fps: float,
    size: tuple[int, int],
    timeout: float,
) -> "np.ndarray":
    """Frames from `start` for `duration` seconds at `fps`, scaled to `size`
    (width, height), as an (n, height, width, 3) uint8 RGB array in memory."""
    import numpy as np

    width, height = size
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *INPUT_GUARDS,
         "-ss", f"{max(start, 0):.3f}", "-i", str(path), "-t", f"{duration:.3f}",
         "-vf", f"fps={fps},scale={width}:{height}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, timeout=timeout, check=False,
    )  # fmt: skip
    if out.returncode != 0:
        last = out.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or ["no details"]
        raise MediaError(f"ffmpeg could not read frames: {last[0]}")
    frame_bytes = width * height * 3
    count = len(out.stdout) // frame_bytes
    return np.frombuffer(out.stdout[: count * frame_bytes], dtype=np.uint8).reshape(
        count, height, width, 3
    )


def extract_image(path: Path, out_path: Path, timeout: float) -> None:
    """Re-encode a screenshot as JPEG (also drops its metadata)."""
    _run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *INPUT_GUARDS,
         "-i", str(path), "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
         "-q:v", "3", "-y", str(out_path)],
        timeout,
    )  # fmt: skip


def extract_audio(path: Path, out_path: Path, *, max_seconds: float, timeout: float) -> None:
    """16 kHz mono 16-bit WAV: what Whisper and the audio models expect."""
    _run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", *INPUT_GUARDS,
         "-i", str(path), "-t", str(max_seconds), "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "pcm_s16le", "-y", str(out_path)],
        timeout,
    )  # fmt: skip
