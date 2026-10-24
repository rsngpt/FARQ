"""Pipeline stages. Each takes the CaseFile so far and returns new Evidence.

Stages marked stub=True are placeholders until their milestone (see PLAN.md);
the runner records them as "stub" so timings never pretend work happened.
"""

from collections.abc import Callable
from dataclasses import dataclass

from farq.domain.casefile import (
    CaseFile,
    Evidence,
    Indicates,
    SourceType,
    Strength,
)
from farq.storage.repo import CaseRepository


@dataclass(frozen=True)
class StageContext:
    repo: CaseRepository


StageFn = Callable[[CaseFile, StageContext], list[Evidence]]


@dataclass(frozen=True)
class Stage:
    name: str
    queue: str  # worker queue this stage belongs on once stages run as separate tasks
    run: StageFn
    stub: bool = False


def no_evidence(case: CaseFile, ctx: StageContext) -> list[Evidence]:
    return []


def lookup_known_fake(case: CaseFile, ctx: StageContext) -> list[Evidence]:
    """Exact-file match against fakes a person already confirmed (sha256).
    Near-duplicate video matching (vpdq) comes in M2."""
    fake = ctx.repo.find_known_fake(case.media_sha256)
    if fake is None:
        return []
    return [
        Evidence(
            stage="lookup",
            type="known_fake_hash",
            source_type=SourceType.MATCH,
            strength=Strength.DECISIVE,
            indicates=Indicates.SCAM,
            human_reviewed=True,
            reason=f"This exact file matches a video already confirmed as fake: {fake.label}.",
            details={
                "sha256": fake.sha256,
                "confirmed_by": fake.confirmed_by,
                "confirmed_at": fake.confirmed_at.isoformat(),
                "source_url": fake.source_url,
            },
        )
    ]


DEFAULT_STAGES: list[Stage] = [
    Stage("ingest", "cpu", no_evidence, stub=True),  # M2: ffprobe, keyframes, 16 kHz audio
    Stage("lookup", "io", lookup_known_fake),
    Stage("extract", "gpu", no_evidence, stub=True),  # M2: OCR, Whisper, entities
    Stage("verify", "io", no_evidence, stub=True),  # M2/M3: official lists, source map
    Stage("analyse", "gpu", no_evidence, stub=True),  # M4: audio-visual binding, audio head
]
