"""The library of genuine recordings the source map compares against."""

import hashlib
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from farq.asr.engine import AsrEngine
from farq.domain.casefile import utcnow
from farq.media import ffmpeg
from farq.media.fingerprints import fingerprint_video
from farq.settings import get_settings
from farq.storage.media import MediaStore
from farq.storage.tables import LibraryClipRow


@dataclass(frozen=True)
class LibraryClip:
    id: UUID
    person: str
    title: str
    source: str
    duration_s: float
    fingerprints: dict[str, Any]
    transcript: dict[str, Any] | None


def add_clip(
    session: Session,
    media: MediaStore,
    asr: AsrEngine,
    path: Path,
    *,
    person: str,
    title: str,
    source: str,
    consent_note: str | None,
) -> tuple[UUID, bool]:
    """Fingerprint and transcribe a genuine clip and store it. Returns
    (clip_id, already_there); the same file is never added twice."""
    sha = _sha256(path)
    existing = session.scalar(select(LibraryClipRow.id).where(LibraryClipRow.sha256 == sha))
    if existing is not None:
        return existing, True

    settings = get_settings()
    info = ffmpeg.probe(path, settings.ffmpeg_timeout_s)
    if info.kind != "video":
        raise ffmpeg.MediaError(f"library clips must be videos, this is {info.kind}")

    clip_id = uuid4()
    with tempfile.TemporaryDirectory(prefix="farq-library-") as tmp:
        work = Path(tmp)
        original = work / f"original{path.suffix.lower()}"
        shutil.copyfile(path, original)
        fingerprints = fingerprint_video(original, work, info.duration_s)
        transcript = None
        if info.audio is not None:
            wav = work / "audio16k.wav"
            ffmpeg.extract_audio(
                original, wav, max_seconds=settings.max_media_seconds,
                timeout=settings.ffmpeg_timeout_s,
            )  # fmt: skip
            transcript = asr.transcribe(wav) | {"model": f"{asr.name} {asr.version}"}
        media_key = f"library/{clip_id}/original{path.suffix.lower()}"
        with original.open("rb") as f:
            media.put(media_key, f, "video/mp4")

    session.add(
        LibraryClipRow(
            id=clip_id,
            person=person,
            title=title,
            source=source,
            consent_note=consent_note,
            media_key=media_key,
            sha256=sha,
            duration_s=info.duration_s or 0.0,
            fingerprints=fingerprints,
            transcript=transcript,
            created_at=utcnow(),
        )
    )
    session.commit()
    return clip_id, False


def load_clips(session: Session) -> list[LibraryClip]:
    rows = session.scalars(select(LibraryClipRow).order_by(LibraryClipRow.created_at))
    return [
        LibraryClip(
            id=r.id,
            person=r.person,
            title=r.title,
            source=r.source,
            duration_s=r.duration_s,
            fingerprints=r.fingerprints,
            transcript=r.transcript,
        )
        for r in rows
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
