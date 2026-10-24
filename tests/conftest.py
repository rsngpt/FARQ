from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from farq.api.deps import get_enqueue, get_media_store, get_session
from farq.api.main import app
from farq.decision.engine import RulesEngine
from farq.domain.casefile import CaseContext, Evidence, Indicates, SourceType, Strength
from farq.settings import get_settings
from farq.storage.repo import CaseRepository
from farq.storage.tables import Base

API_KEY = "test-api-key"


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fixed test values that override anything in .env."""
    monkeypatch.setenv("USER_HASH_KEY", "test-hash-key")
    monkeypatch.setenv("INTAKE_API_KEY", API_KEY)
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def repo(session: Session) -> CaseRepository:
    return CaseRepository(session)


@pytest.fixture
def rules() -> RulesEngine:
    return RulesEngine.from_file(get_settings().rules_path)


class InMemoryMediaStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, fileobj: BinaryIO, content_type: str) -> None:
        self.objects[key] = fileobj.read()

    def download(self, key: str, path: Path) -> None:
        path.write_bytes(self.objects[key])


@pytest.fixture
def media() -> InMemoryMediaStore:
    return InMemoryMediaStore()


@pytest.fixture
def queued() -> list[UUID]:
    """Case IDs the API queued; tests run the pipeline themselves."""
    return []


@pytest.fixture
def client(session: Session, media: InMemoryMediaStore, queued: list[UUID]) -> Iterator[TestClient]:
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_media_store] = lambda: media
    app.dependency_overrides[get_enqueue] = lambda: queued.append
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_evidence() -> Callable[..., Evidence]:
    def _make(**overrides) -> Evidence:
        fields = {
            "stage": "test",
            "type": "test_signal",
            "source_type": SourceType.MODEL,
            "strength": Strength.STRONG,
            "indicates": Indicates.SCAM,
            "reason": "A test signal.",
        }
        return Evidence(**(fields | overrides))

    return _make


@pytest.fixture
def new_case(repo: CaseRepository) -> Callable[..., UUID]:
    counter = iter(range(1_000_000))

    def _new(sha256: str = "a" * 64, money_sent: bool | None = None) -> UUID:
        case_id, _ = repo.create_case(
            channel="test",
            message_id=f"msg-{next(counter)}",
            user_hash="h" * 64,
            media_sha256=sha256,
            media_bytes=10,
            media_extension=".mp4",
            context=CaseContext(money_sent=money_sent),
        )
        return case_id

    return _new
