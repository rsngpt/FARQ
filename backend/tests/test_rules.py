import pytest
from pydantic import ValidationError

from farq.decision.engine import RuleSet
from farq.domain.casefile import Indicates, SourceType, Strength, Verdict


def test_known_fake_match_is_confirmed(rules, make_evidence):
    ev = make_evidence(
        type="known_fake_hash",
        source_type=SourceType.MATCH,
        strength=Strength.DECISIVE,
        human_reviewed=True,
    )
    decision = rules.decide([ev])
    assert decision.verdict == Verdict.CONFIRMED_SCAM
    assert decision.rule_id == "known_fake_match"
    assert decision.evidence_ids == [ev.id]
    assert not decision.needs_review


def test_decisive_match_without_human_review_is_not_confirmed(rules, make_evidence):
    ev = make_evidence(
        type="known_fake_hash", source_type=SourceType.MATCH, strength=Strength.DECISIVE
    )
    assert rules.decide([ev]).verdict != Verdict.CONFIRMED_SCAM


def test_strong_signals_from_two_kinds_of_source_are_likely_and_need_review(rules, make_evidence):
    a = make_evidence(source_type=SourceType.MODEL)
    b = make_evidence(source_type=SourceType.MATCH)
    decision = rules.decide([a, b])
    assert decision.verdict == Verdict.LIKELY_SCAM
    assert decision.needs_review
    assert set(decision.evidence_ids) == {a.id, b.id}


def test_strong_signals_of_one_kind_abstain(rules, make_evidence):
    a = make_evidence(source_type=SourceType.MODEL)
    b = make_evidence(source_type=SourceType.MODEL)
    assert rules.decide([a, b]).verdict == Verdict.NOT_VERIFIED


def test_strong_counter_evidence_abstains(rules, make_evidence):
    a = make_evidence(source_type=SourceType.MODEL)
    b = make_evidence(source_type=SourceType.MATCH)
    against = make_evidence(source_type=SourceType.MATCH, indicates=Indicates.NOT_SCAM)
    decision = rules.decide([a, b, against])
    assert decision.verdict == Verdict.NOT_VERIFIED
    assert against.id not in decision.evidence_ids  # warning signs only


def test_weak_signals_never_decide(rules, make_evidence):
    weak = [
        make_evidence(source_type=s, strength=Strength.WEAK)
        for s in (SourceType.MODEL, SourceType.MATCH, SourceType.LIST)
    ]
    decision = rules.decide(weak)
    assert decision.verdict == Verdict.NOT_VERIFIED
    assert decision.rule_id == "abstain"
    assert decision.evidence_ids == [e.id for e in weak]  # shown as warning signs


def test_no_evidence_abstains(rules):
    decision = rules.decide([])
    assert decision.verdict == Verdict.NOT_VERIFIED
    assert decision.evidence_ids == []


def test_rules_version_is_a_short_file_hash(rules):
    assert len(rules.version) == 12
    assert rules.decide([]).rules_version == rules.version


ABSTAIN = {"id": "abstain", "description": "-", "verdict": "not_verified", "when": []}


def test_confirmed_rule_must_require_human_review():
    unsafe = {
        "id": "unsafe",
        "description": "-",
        "verdict": "confirmed_scam",
        "when": [{"evidence": {"min_strength": "decisive"}}],
    }
    with pytest.raises(ValidationError, match="human_reviewed"):
        RuleSet.model_validate({"rules": [unsafe, ABSTAIN]})


def test_last_rule_must_be_abstain():
    likely = {
        "id": "likely",
        "description": "-",
        "verdict": "likely_scam",
        "when": [{"evidence": {"min_strength": "strong"}}],
    }
    with pytest.raises(ValidationError, match="abstain"):
        RuleSet.model_validate({"rules": [ABSTAIN, likely]})


def test_unknown_rule_keys_are_rejected():
    typo = ABSTAIN | {"verdcit": "likely_scam"}
    with pytest.raises(ValidationError):
        RuleSet.model_validate({"rules": [typo]})
