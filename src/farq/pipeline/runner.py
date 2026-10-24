import logging
from uuid import UUID

from farq.channels.responder import compose_reply
from farq.decision.engine import RulesEngine
from farq.domain.casefile import CaseFile, CaseStatus, StageStatus, StageTiming, utcnow
from farq.pipeline.stages import DEFAULT_STAGES, Stage, StageContext
from farq.storage.repo import CaseRepository

logger = logging.getLogger(__name__)


def run_pipeline(
    case_id: UUID,
    repo: CaseRepository,
    rules: RulesEngine,
    stages: list[Stage] = DEFAULT_STAGES,
) -> CaseFile:
    """Run every stage, then decide and compose the reply.

    Safe to run twice: a decided case is returned as is, and stages that already
    finished are skipped, so a worker that crashed halfway can simply retry.
    A stage that raises is recorded as failed; the case still gets a verdict
    from whatever evidence exists (usually NOT VERIFIED).
    """
    case = _load(repo, case_id)
    if case.status == CaseStatus.DECIDED:
        return case

    try:
        repo.set_status(case_id, CaseStatus.PROCESSING)
        repo.commit()
        finished = repo.finished_stages(case_id)
        ctx = StageContext(repo=repo)

        for stage in stages:
            if stage.name in finished:
                continue
            started = utcnow()
            error = None
            try:
                evidence = stage.run(case, ctx)
                status = StageStatus.STUB if stage.stub else StageStatus.OK
            except Exception as exc:
                logger.exception("stage %s failed for case %s", stage.name, case_id)
                evidence, status, error = [], StageStatus.FAILED, f"{type(exc).__name__}: {exc}"
            repo.replace_stage_evidence(case_id, stage.name, evidence)
            repo.record_stage(
                case_id,
                StageTiming(
                    stage=stage.name,
                    status=status,
                    started_at=started,
                    ended_at=utcnow(),
                    error=error,
                ),
            )
            repo.commit()
            case = _load(repo, case_id)  # later stages see earlier evidence

        started = utcnow()
        decision = rules.decide(case.evidence)
        reply = compose_reply(case, decision)
        cited = case.evidence_by_ids(decision.evidence_ids)
        repo.save_decision(case_id, decision, reply)
        repo.record_stage(
            case_id,
            StageTiming(
                stage="decide", status=StageStatus.OK, started_at=started, ended_at=utcnow()
            ),
        )
        repo.add_audit(
            actor="rules-engine",
            action="verdict",
            case_id=case_id,
            verdict=decision.verdict,
            evidence_ids=decision.evidence_ids,
            model_versions=sorted(
                {f"{e.model_name}@{e.model_version}" for e in cited if e.model_name}
            ),
            details={"rule_id": decision.rule_id, "rules_version": decision.rules_version},
        )
        repo.commit()
    except Exception:
        repo.rollback()
        repo.set_status(case_id, CaseStatus.FAILED)
        repo.commit()
        raise
    return _load(repo, case_id)


def _load(repo: CaseRepository, case_id: UUID) -> CaseFile:
    case = repo.load(case_id)
    if case is None:
        raise LookupError(f"case {case_id} not found")
    return case
