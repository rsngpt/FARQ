from celery import Celery

from farq.settings import get_settings

settings = get_settings()

# Three queues: io (network, storage), cpu (OCR, ffmpeg), gpu (model inference).
# Each worker container listens to one queue; see docker-compose.yml.
app = Celery("farq", broker=settings.redis_url, backend=settings.redis_url)
app.conf.update(
    task_default_queue="io",
    # Take one job at a time and acknowledge it only when done, so a crashed
    # worker's job is retried and a GPU worker never holds two models' jobs.
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)


@app.task(name="farq.ping")
def ping() -> str:
    """Smoke-test task: proves a worker is consuming its queue."""
    return "pong"
