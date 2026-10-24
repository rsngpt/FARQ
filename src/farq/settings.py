from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """App configuration, read from environment variables or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    redis_url: str = "redis://127.0.0.1:6379/0"

    postgres_user: str = "farq"
    postgres_password: SecretStr = SecretStr("")
    postgres_db: str = "farq"
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and
    # hangs, because Docker only publishes the port on IPv4.
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    s3_endpoint_url: str = "http://127.0.0.1:8333"
    s3_access_key: str = ""
    s3_secret_key: SecretStr = SecretStr("")
    s3_bucket: str = "farq-media"

    # Key for hashing phone numbers / chat IDs. Raw IDs are never stored.
    user_hash_key: SecretStr = SecretStr("")
    # Shared key for the local upload endpoint (X-API-Key header).
    intake_api_key: SecretStr = SecretStr("")
    max_upload_mb: int = 64

    # Ingest limits: only the first max_media_seconds are processed.
    max_media_seconds: float = 600
    max_keyframes: int = 120
    ffmpeg_timeout_s: float = 120

    # Frame fingerprints (PDQ) for the source map: frames per second, and a cap
    # (longer videos are sampled more thinly).
    fingerprint_fps: float = 2.0
    max_fingerprint_frames: int = 600

    # OCR: frames read per video (spread evenly), minimum confidence kept, and
    # the long side frames are shrunk to before text detection.
    ocr_max_frames: int = 12
    ocr_min_score: float = 0.6
    ocr_det_side: int = 736

    # Whisper: our own conversion of OpenAI's weights (scripts/convert_whisper.py).
    # int8 weights with float16 maths on the GPU; plain int8 on CPU.
    whisper_model_dir: Path = REPO_ROOT / "models" / "whisper-large-v3-turbo-ct2"
    whisper_gpu_compute_type: str = "int8_float16"
    whisper_beam_size: int = 5

    # Models a worker loads at start-up, comma-separated (e.g. "whisper"), so
    # the first case doesn't wait for the load. Set on the GPU worker only.
    preload_models: str = ""

    rules_path: Path = REPO_ROOT / "config" / "rules" / "verdicts.yaml"

    # Queue that GPU stages are sent to. Set to "cpu" on machines without an
    # NVIDIA GPU (and leave out the gpu compose profile); they then run slowly.
    gpu_queue: str = "gpu"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
