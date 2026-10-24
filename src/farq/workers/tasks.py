from uuid import UUID

from farq.decision.engine import get_rules_engine
from farq.pipeline.runner import run_pipeline
from farq.storage.db import get_sessionmaker
from farq.storage.repo import CaseRepository
from farq.workers.celery_app import app


@app.task(name="farq.run_case")
def run_case(case_id: str) -> str:
    """Run the whole pipeline for one case. Stages will move to their own
    queues (cpu / gpu) as they become real; for now everything runs on io."""
    with get_sessionmaker()() as session:
        case = run_pipeline(UUID(case_id), CaseRepository(session), get_rules_engine())
    return case.status
