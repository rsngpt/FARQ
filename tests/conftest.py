import hashlib
import shutil
import subprocess
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
from farq.ocr.engine import TextLine
from farq.settings import get_settings
from farq.storage.repo import CaseRepository, media_key_for
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


class FakeOcrEngine:
    """Stand-in for PaddleOCR: returns `lines_for(frame_index)` for each image."""

    name = "fake-ocr"
    version = "test"

    def __init__(self) -> None:
        self.lines_for: Callable[[int], list[TextLine]] = lambda i: []
        self.images_read: list[Path] = []

    def read(self, images: list[Path]) -> list[list[TextLine]]:
        self.images_read += images
        return [self.lines_for(i) for i in range(len(images))]


@pytest.fixture(autouse=True)
def fake_ocr(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Tests use the stand-in OCR unless marked real_models."""
    if request.node.get_closest_marker("real_models"):
        yield None
        return
    engine = FakeOcrEngine()
    monkeypatch.setattr("farq.pipeline.ocr.get_ocr_engine", lambda det_side: engine)
    yield engine


class FakeAsrEngine:
    """Stand-in for Whisper: returns `result` for every file."""

    name = "fake-asr"
    version = "test"

    def __init__(self) -> None:
        self.result: dict = {
            "language": "en",
            "language_probability": 0.9,
            "duration_s": 0.0,
            "speech_s": 0.0,
            "text": "",
            "segments": [],
        }
        self.files_heard: list[Path] = []

    def transcribe(self, wav: Path) -> dict:
        self.files_heard.append(wav)
        return self.result


@pytest.fixture(autouse=True)
def fake_asr(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Tests use the stand-in speech-to-text unless marked real_models."""
    if request.node.get_closest_marker("real_models"):
        yield None
        return
    engine = FakeAsrEngine()
    monkeypatch.setattr("farq.pipeline.transcribe.get_asr_engine", lambda *a: engine)
    yield engine


@pytest.fixture
def set_setting(monkeypatch: pytest.MonkeyPatch) -> Callable[[str, str], None]:
    """Change one setting for this test (settings are cached, so clear the cache)."""

    def _set(name: str, value: str) -> None:
        monkeypatch.setenv(name, value)
        get_settings.cache_clear()

    return _set


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


def ffmpeg_make(out: Path, *args: str) -> bytes:
    """Generate a synthetic media file with FFmpeg (test patterns, tones)."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg is not on PATH; see README (winget install Gyan.FFmpeg)")
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", *args, str(out)], check=True, capture_output=True
    )
    return out.read_bytes()


def synthetic_video(out: Path, seconds: int, with_audio: bool = True) -> bytes:
    video = ["-f", "lavfi", "-i", f"testsrc=duration={seconds}:size=320x240:rate=10"]
    audio = ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"] if with_audio else []
    return ffmpeg_make(out, *video, *audio, "-shortest")


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """A 3-second test-pattern video with a tone."""
    return synthetic_video(tmp_path_factory.mktemp("media") / "sample.mp4", seconds=3)


@pytest.fixture
def new_case(
    repo: CaseRepository, media: InMemoryMediaStore, sample_video: bytes
) -> Callable[..., UUID]:
    """Create a case whose media is in the store, as intake would leave it."""
    counter = iter(range(1_000_000))

    def _new(
        content: bytes | None = None,
        extension: str = ".mp4",
        money_sent: bool | None = None,
        sha256: str | None = None,
    ) -> UUID:
        content = sample_video if content is None else content
        case_id, _ = repo.create_case(
            channel="test",
            message_id=f"msg-{next(counter)}",
            user_hash="h" * 64,
            media_sha256=sha256 or hashlib.sha256(content).hexdigest(),
            media_bytes=len(content),
            media_extension=extension,
            context=CaseContext(money_sent=money_sent),
        )
        media.objects[media_key_for(case_id, extension)] = content
        return case_id

    return _new
