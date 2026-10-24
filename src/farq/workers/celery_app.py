import logging
import time

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from farq.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Three queues: io (network, storage), cpu (OCR, ffmpeg), gpu (model inference).
# Each worker container listens to one queue; see docker-compose.yml.
app = Celery(
    "farq",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["farq.workers.tasks"],
)
app.conf.update(
    task_default_queue="io",
    # Take one job at a time and acknowledge it only when done, so a crashed
    # worker's job is retried and a GPU worker never holds two models' jobs.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


def _wanted() -> set[str]:
    return {m.strip() for m in get_settings().preload_models.split(",") if m.strip()}


def _log_loaded(engine: object, started: float) -> None:
    logger.info("preloaded %s (%s) in %.1f s", engine.name, engine.version,
                time.perf_counter() - started)  # fmt: skip


# Load the models in PRELOAD_MODELS before taking jobs, in the process that will
# run the jobs, so the first case doesn't wait for a model to load.


@worker_ready.connect
def preload_whisper(**_: object) -> None:
    """GPU worker (solo pool): jobs run in this same process."""
    if "whisper" in _wanted():
        from farq.asr.engine import get_asr_engine

        s = get_settings()
        started = time.perf_counter()
        engine = get_asr_engine(s.whisper_model_dir, s.whisper_gpu_compute_type,
                                s.whisper_beam_size)  # fmt: skip
        _log_loaded(engine, started)


@worker_process_init.connect
def preload_ocr(**_: object) -> None:
    """CPU worker (prefork pool): each child process loads its own copy."""
    if "ocr" in _wanted():
        from farq.ocr.engine import get_ocr_engine

        started = time.perf_counter()
        _log_loaded(get_ocr_engine(get_settings().ocr_det_side), started)


@app.task(name="farq.ping")
def ping() -> str:
    """Smoke-test task: proves a worker is consuming its queue."""
    return "pong"
