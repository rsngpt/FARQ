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
def preload_gpu_worker_models(**_: object) -> None:
    """GPU worker (solo pool): jobs run in this same process."""
    s = get_settings()
    if "whisper" in _wanted():
        from farq.asr.engine import get_asr_engine

        started = time.perf_counter()
        engine = get_asr_engine(s.whisper_model_dir, s.whisper_gpu_compute_type,
                                s.whisper_beam_size)  # fmt: skip
        _log_loaded(engine, started)
    if "bge" in _wanted():
        from farq.embed import get_embedder

        started = time.perf_counter()
        _log_loaded(get_embedder(s.bge_m3_dir, s.bge_m3_revision, s.embed_threads), started)
    if "binding" in _wanted():
        # The face model, and librosa's one-off code compilation (measured 8.2 s on
        # the first call, 0.06 s after), so the first case doesn't pay for them.
        import numpy as np

        from farq.binding import audio_emphasis
        from farq.sourcemap.original import get_face_finder

        started = time.perf_counter()
        finder = get_face_finder(s.face_model_path)
        audio_emphasis(np.zeros(5 * 16000, dtype=np.float32))
        _log_loaded(finder, started)


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
