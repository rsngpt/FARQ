"""Rules engine: turns Evidence rows into a verdict using config/rules/verdicts.yaml.

The verdict is set here and only here. No model or LLM sets it.
"""

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from farq.domain.casefile import (
    Decision,
    Evidence,
    Indicates,
    SourceType,
    Strength,
    Verdict,
)
from farq.settings import get_settings


class EvidenceFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    source_type: SourceType | None = None
    min_strength: Strength = Strength.WEAK
    indicates: Indicates | None = None
    human_reviewed: bool | None = None

    def matches(self, e: Evidence) -> bool:
        return (
            (self.type is None or e.type == self.type)
            and (self.source_type is None or e.source_type == self.source_type)
            and e.strength.rank >= self.min_strength.rank
            and (self.indicates is None or e.indicates == self.indicates)
            and (self.human_reviewed is None or e.human_reviewed == self.human_reviewed)
        )


class Clause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence: EvidenceFilter | None = None
    distinct_source_types: int = Field(default=1, ge=1)
    no_evidence: EvidenceFilter | None = None

    @model_validator(mode="after")
    def _exactly_one_kind(self) -> "Clause":
        if (self.evidence is None) == (self.no_evidence is None):
            raise ValueError("a condition needs exactly one of 'evidence' or 'no_evidence'")
        return self

    def evaluate(self, evidence: list[Evidence]) -> list[Evidence] | None:
        """The evidence this condition cites if it holds, or None if it doesn't."""
        if self.evidence is not None:
            matched = [e for e in evidence if self.evidence.matches(e)]
            kinds = {e.source_type for e in matched}
            return matched if matched and len(kinds) >= self.distinct_source_types else None
        assert self.no_evidence is not None
        return None if any(self.no_evidence.matches(e) for e in evidence) else []


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    verdict: Verdict
    review: bool = False
    when: list[Clause]


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[Rule]

    @model_validator(mode="after")
    def _safety_checks(self) -> "RuleSet":
        ids = [r.id for r in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("rule ids must be unique")
        if not self.rules or self.rules[-1].when or self.rules[-1].verdict != Verdict.NOT_VERIFIED:
            raise ValueError("the last rule must be the abstain rule: no conditions, not_verified")
        for rule in self.rules[:-1]:
            if not rule.when:
                raise ValueError(f"rule {rule.id!r} has no conditions; only the last rule may")
            if rule.verdict == Verdict.CONFIRMED_SCAM and not any(
                c.evidence is not None and c.evidence.human_reviewed for c in rule.when
            ):
                raise ValueError(
                    f"rule {rule.id!r}: confirmed_scam requires human_reviewed evidence"
                )
        return self


class RulesEngine:
    def __init__(self, ruleset: RuleSet, version: str):
        self.ruleset = ruleset
        self.version = version  # first 12 hex chars of the rules file's SHA-256

    @classmethod
    def from_file(cls, path: Path) -> "RulesEngine":
        raw = path.read_bytes()
        ruleset = RuleSet.model_validate(yaml.safe_load(raw))
        return cls(ruleset, hashlib.sha256(raw).hexdigest()[:12])

    def decide(self, evidence: list[Evidence]) -> Decision:
        for rule in self.ruleset.rules:
            cited: list[Evidence] = []
            for clause in rule.when:
                result = clause.evaluate(evidence)
                if result is None:
                    break
                cited.extend(result)
            else:
                if not rule.when:
                    # Abstain: cite whatever points to a scam, as warning signs.
                    cited = [e for e in evidence if e.indicates == Indicates.SCAM]
                return Decision(
                    verdict=rule.verdict,
                    rule_id=rule.id,
                    evidence_ids=list(dict.fromkeys(e.id for e in cited)),
                    needs_review=rule.review,
                    rules_version=self.version,
                )
        raise AssertionError("unreachable: the last rule always matches")


@lru_cache
def get_rules_engine() -> RulesEngine:
    return RulesEngine.from_file(get_settings().rules_path)
