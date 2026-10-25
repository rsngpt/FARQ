from uuid import UUID

from farq.api.deps import get_media_store
from farq.decision.engine import get_rules_engine
from farq.pipeline.runner import run_next_stage
from farq.pipeline.stages import DEFAULT_STAGES
from farq.settings import get_settings
from farq.storage.db import get_sessionmaker
from farq.storage.repo import CaseRepository
from farq.workers.celery_app import app


def resolve_queue(queue: str) -> str:
    return get_settings().gpu_queue if queue == "gpu" else queue


def enqueue_case(case_id: UUID) -> None:
    """Start a new case on the first stage's queue."""
    run_case.apply_async(args=[str(case_id)], queue=resolve_queue(DEFAULT_STAGES[0].queue))


@app.task(name="farq.run_case")
def run_case(case_id: str) -> str | None:
    """Run one stage, then hand the case to the queue of the next stage."""
    with get_sessionmaker()() as session:
        next_queue = run_next_stage(
            UUID(case_id), CaseRepository(session), get_rules_engine(), get_media_store()
        )
    if next_queue is not None:
        run_case.apply_async(args=[case_id], queue=resolve_queue(next_queue))
    return next_queue
