"""Ingest stage: check the file, then cut it into what later stages need:
keyframes with timestamps (OCR, source matching) and 16 kHz mono audio
(Whisper, audio models)."""

import hashlib
from pathlib import Path, PurePath

from farq.domain.casefile import Artifact, CaseFile
from farq.media import ffmpeg
from farq.media.ffmpeg import MediaError
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings


def ingest(case: CaseFile, ctx: StageContext) -> StageOutput:
    settings = get_settings()
    timeout = settings.ffmpeg_timeout_s
    original = ctx.workdir / f"input{PurePath(case.media_key).suffix}"
    ctx.media.download(case.media_key, original)
    if _sha256(original) != case.media_sha256:
        raise MediaError("the stored file doesn't match the fingerprint taken at upload")

    info = ffmpeg.probe(original, timeout)
    tool = {"model_name": "ffmpeg", "model_version": ffmpeg.version()}
    media_info = info.as_dict()
    if info.duration_s and info.duration_s > settings.max_media_seconds:
        media_info["processed_s"] = settings.max_media_seconds
    artifacts = [Artifact(stage="ingest", kind="media_info", data=media_info, **tool)]

    if info.kind == "video":
        frames_dir = ctx.workdir / "frames"
        frames_dir.mkdir()
        fps, frames = ffmpeg.extract_frames(
            original,
            frames_dir,
            duration_s=info.duration_s,
            max_frames=settings.max_keyframes,
            max_seconds=settings.max_media_seconds,
            timeout=timeout,
        )
        artifacts.append(_keyframes(case, ctx, fps, frames, tool))
    elif info.kind == "image":
        still = ctx.workdir / "00001.jpg"
        ffmpeg.extract_image(original, still, timeout)
        artifacts.append(_keyframes(case, ctx, None, [(0.0, still)], tool))

    if info.audio is not None:
        wav = ctx.workdir / "audio16k.wav"
        ffmpeg.extract_audio(original, wav, max_seconds=settings.max_media_seconds, timeout=timeout)
        key = f"cases/{case.id}/audio16k.wav"
        with wav.open("rb") as f:
            ctx.media.put(key, f, "audio/wav")
        artifacts.append(
            Artifact(
                stage="ingest",
                kind="audio_16k",
                storage_key=key,
                data={"sample_rate": 16000, "channels": 1, "bytes": wav.stat().st_size},
                **tool,
            )
        )
    return StageOutput(artifacts=artifacts)


def _keyframes(
    case: CaseFile,
    ctx: StageContext,
    fps: float | None,
    frames: list[tuple[float, Path]],
    tool: dict[str, str],
) -> Artifact:
    stored = []
    for t, path in frames:
        key = f"cases/{case.id}/keyframes/{path.name}"
        with path.open("rb") as f:
            ctx.media.put(key, f, "image/jpeg")
        stored.append({"t": round(t, 3), "key": key})
    return Artifact(stage="ingest", kind="keyframes", data={"fps": fps, "frames": stored}, **tool)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
