import logging
import tempfile
from pathlib import Path
from uuid import UUID

from farq.channels.responder import compose_reply
from farq.decision.engine import RulesEngine
from farq.domain.casefile import CaseFile, CaseStatus, StageStatus, StageTiming, utcnow
from farq.pipeline.stages import DEFAULT_STAGES, Stage, StageContext, StageOutput
from farq.storage.media import MediaStore
from farq.storage.repo import CaseRepository

logger = logging.getLogger(__name__)


def run_next_stage(
    case_id: UUID,
    repo: CaseRepository,
    rules: RulesEngine,
    media: MediaStore,
    stages: list[Stage] = DEFAULT_STAGES,
) -> str | None:
    """Run the case's next stage. Returns the queue the following stage belongs
    on, or None once the case is decided (the last stage also decides).

    Safe to call again for the same case: a decided case does nothing, and stages
    with a recorded run are skipped, so a crashed worker's job can simply retry.
    A stage that raises is recorded as failed; the case still gets a verdict
    from whatever evidence exists (usually NOT VERIFIED).
    """
    case = _load(repo, case_id)
    if case.status == CaseStatus.DECIDED:
        return None
    try:
        if case.status != CaseStatus.PROCESSING:
            repo.set_status(case_id, CaseStatus.PROCESSING)
            repo.commit()
        already_run = repo.stages_run(case_id)
        pending = [s for s in stages if s.name not in already_run]
        if pending:
            _run_stage(pending[0], case, repo, media)
            if len(pending) > 1:
                return pending[1].queue
        _decide(_load(repo, case_id), repo, rules)
        return None
    except Exception:
        repo.rollback()
        repo.set_status(case_id, CaseStatus.FAILED)
        repo.commit()
        raise


def run_pipeline(
    case_id: UUID,
    repo: CaseRepository,
    rules: RulesEngine,
    media: MediaStore,
    stages: list[Stage] = DEFAULT_STAGES,
) -> CaseFile:
    """Run every remaining stage in this process (tests, scripts)."""
    while run_next_stage(case_id, repo, rules, media, stages) is not None:
        pass
    return _load(repo, case_id)


def _run_stage(stage: Stage, case: CaseFile, repo: CaseRepository, media: MediaStore) -> None:
    started = utcnow()
    error = None
    with tempfile.TemporaryDirectory(prefix=f"farq-{stage.name}-") as tmp:
        ctx = StageContext(repo=repo, media=media, workdir=Path(tmp))
        try:
            output = stage.run(case, ctx)
            status = StageStatus.STUB if stage.stub else StageStatus.OK
        except Exception as exc:
            logger.exception("stage %s failed for case %s", stage.name, case.id)
            output, status, error = (
                StageOutput(),
                StageStatus.FAILED,
                f"{type(exc).__name__}: {exc}",
            )
    repo.replace_stage_outputs(case.id, stage.name, output.evidence, output.artifacts)
    repo.record_stage(
        case.id,
        StageTiming(
            stage=stage.name, status=status, started_at=started, ended_at=utcnow(), error=error
        ),
    )
    repo.commit()


def _decide(case: CaseFile, repo: CaseRepository, rules: RulesEngine) -> None:
    started = utcnow()
    decision = rules.decide(case.evidence)
    reply = compose_reply(case, decision)
    cited = case.evidence_by_ids(decision.evidence_ids)
    repo.save_decision(case.id, decision, reply)
    repo.record_stage(
        case.id,
        StageTiming(stage="decide", status=StageStatus.OK, started_at=started, ended_at=utcnow()),
    )
    repo.add_audit(
        actor="rules-engine",
        action="verdict",
        case_id=case.id,
        verdict=decision.verdict,
        evidence_ids=decision.evidence_ids,
        model_versions=sorted({f"{e.model_name}@{e.model_version}" for e in cited if e.model_name}),
        details={"rule_id": decision.rule_id, "rules_version": decision.rules_version},
    )
    repo.commit()


def _load(repo: CaseRepository, case_id: UUID) -> CaseFile:
    case = repo.load(case_id)
    if case is None:
        raise LookupError(f"case {case_id} not found")
    return case
