"""Intake: one entry point for every channel (local upload now; Telegram and
WhatsApp later). Hashes the sender, dedupes on message ID, stores the media,
creates the case and queues the pipeline."""

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath
from typing import BinaryIO
from uuid import UUID

from farq.domain.casefile import CaseContext, CaseStatus
from farq.privacy import hash_user_id
from farq.storage.media import MediaStore
from farq.storage.repo import CaseRepository, media_key_for

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    # video
    ".mp4", ".mov", ".webm", ".mkv", ".3gp",
    # audio / voice notes
    ".ogg", ".opus", ".mp3", ".m4a", ".wav", ".aac",
    # screenshots
    ".jpg", ".jpeg", ".png", ".webp",
}  # fmt: skip

CHUNK = 1024 * 1024

Enqueue = Callable[[UUID], object]


class IntakeError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class IntakeResult:
    case_id: UUID
    duplicate: bool


def submit_media(
    *,
    repo: CaseRepository,
    media: MediaStore,
    enqueue: Enqueue,
    channel: str,
    message_id: str,
    user_id: str,
    user_hash_key: str,
    filename: str,
    fileobj: BinaryIO,
    content_type: str,
    context: CaseContext,
    max_bytes: int,
) -> IntakeResult:
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise IntakeError(415, f"Unsupported file type {extension or '(none)'!r}")

    sha256, size = _hash_and_measure(fileobj, max_bytes)
    if size == 0:
        raise IntakeError(400, "The file is empty")

    case_id, duplicate = repo.create_case(
        channel=channel,
        message_id=message_id,
        user_hash=hash_user_id(user_id, user_hash_key),
        media_sha256=sha256,
        media_bytes=size,
        media_extension=extension,
        context=context,
    )
    if duplicate:
        return IntakeResult(case_id, duplicate=True)

    try:
        fileobj.seek(0)
        media.put(media_key_for(case_id, extension), fileobj, content_type)
    except Exception as exc:
        logger.exception("storing media failed for case %s", case_id)
        repo.set_status(case_id, CaseStatus.FAILED)
        repo.commit()
        raise IntakeError(502, "Could not store the file; please try again") from exc

    enqueue(case_id)
    return IntakeResult(case_id, duplicate=False)


def _hash_and_measure(fileobj: BinaryIO, max_bytes: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := fileobj.read(CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise IntakeError(413, f"File is larger than {max_bytes // (1024 * 1024)} MB")
        digest.update(chunk)
    return digest.hexdigest(), size
