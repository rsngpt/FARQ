import hmac
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from farq.intake import Enqueue
from farq.settings import Settings, get_settings
from farq.storage.db import get_sessionmaker
from farq.storage.media import MediaStore, S3MediaStore
from farq.storage.repo import CaseRepository


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def get_repo(session: Annotated[Session, Depends(get_session)]) -> CaseRepository:
    return CaseRepository(session)


@lru_cache
def get_media_store() -> MediaStore:
    store = S3MediaStore.from_settings(get_settings())
    store.ensure_bucket()
    return store


def get_enqueue() -> Enqueue:
    from farq.workers.tasks import enqueue_case

    return enqueue_case


def require_api_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.intake_api_key.get_secret_value()
    if not expected or x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(401, "Missing or wrong X-API-Key")


SettingsDep = Annotated[Settings, Depends(get_settings)]
RepoDep = Annotated[CaseRepository, Depends(get_repo)]
MediaDep = Annotated[MediaStore, Depends(get_media_store)]
EnqueueDep = Annotated[Enqueue, Depends(get_enqueue)]
