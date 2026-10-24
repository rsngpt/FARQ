import pytest

from farq.domain.casefile import CaseStatus, StageStatus, Verdict
from farq.pipeline.runner import run_pipeline
from farq.pipeline.stages import DEFAULT_STAGES, Stage


def test_runs_every_stage_and_decides(repo, rules, new_case):
    case = run_pipeline(new_case(), repo, rules)
    assert case.status == CaseStatus.DECIDED
    assert [t.stage for t in case.timings] == [s.name for s in DEFAULT_STAGES] + ["decide"]
    stubs = {t.stage for t in case.timings if t.status == StageStatus.STUB}
    assert stubs == {"ingest", "extract", "verify", "analyse"}
    assert case.decision.verdict == Verdict.NOT_VERIFIED
    assert "NOT VERIFIED" in case.reply_text
    assert "does not mean it is genuine" in case.reply_text


def test_known_fake_is_confirmed(repo, rules, new_case):
    repo.add_known_fake(sha256="b" * 64, label="test fake video", confirmed_by="reviewer:test")
    repo.commit()
    case = run_pipeline(new_case(sha256="b" * 64), repo, rules)
    assert case.decision.verdict == Verdict.CONFIRMED_SCAM
    assert "CONFIRMED SCAM" in case.reply_text
    assert "test fake video" in case.reply_text  # the cited reason


def test_verdict_writes_an_audit_row(repo, rules, new_case):
    repo.add_known_fake(sha256="b" * 64, label="test fake", confirmed_by="reviewer:test")
    repo.commit()
    case = run_pipeline(new_case(sha256="b" * 64), repo, rules)
    [row] = repo.list_audit(case.id)
    assert row.actor == "rules-engine"
    assert row.action == "verdict"
    assert row.verdict == "confirmed_scam"
    assert row.evidence_ids == case.decision.evidence_ids
    assert row.details["rules_version"] == rules.version


def test_running_twice_changes_nothing(repo, rules, new_case):
    case_id = new_case()
    first = run_pipeline(case_id, repo, rules)
    second = run_pipeline(case_id, repo, rules)
    assert second.decision == first.decision
    assert len(second.evidence) == len(first.evidence)
    assert len(repo.list_audit(case_id)) == 1


class WorkerCrash(BaseException):
    """Stands in for a worker being killed mid-stage (not a normal error)."""


def test_retry_after_crash_skips_finished_stages(repo, rules, new_case):
    calls: list[str] = []

    def ok(name):
        def run(case, ctx):
            calls.append(name)
            return []

        return run

    def crash(case, ctx):
        raise WorkerCrash

    case_id = new_case()
    with pytest.raises(WorkerCrash):
        run_pipeline(
            case_id, repo, rules, [Stage("one", "io", ok("one")), Stage("two", "io", crash)]
        )
    assert repo.load(case_id).status == CaseStatus.PROCESSING

    case = run_pipeline(
        case_id, repo, rules, [Stage("one", "io", ok("one")), Stage("two", "io", ok("two"))]
    )
    assert calls == ["one", "two"]  # "one" was not re-run
    assert case.status == CaseStatus.DECIDED


def test_failed_stage_is_recorded_and_case_abstains(repo, rules, new_case):
    def broken(case, ctx):
        raise RuntimeError("model not loaded")

    case = run_pipeline(new_case(), repo, rules, [Stage("broken", "gpu", broken)])
    [timing] = [t for t in case.timings if t.stage == "broken"]
    assert timing.status == StageStatus.FAILED
    assert timing.error == "RuntimeError: model not loaded"
    assert case.decision.verdict == Verdict.NOT_VERIFIED


def test_money_sent_puts_1930_first(repo, rules, new_case):
    case = run_pipeline(new_case(money_sent=True), repo, rules)
    assert case.reply_text.splitlines()[0].startswith("If you have already sent money: call 1930")


def test_no_money_sent_has_no_1930_banner(repo, rules, new_case):
    case = run_pipeline(new_case(money_sent=False), repo, rules)
    assert not case.reply_text.startswith("If you have already sent money")
