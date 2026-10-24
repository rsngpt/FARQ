"""Pipeline stages. Each takes the CaseFile so far and returns new evidence and
artifacts. Stages run one at a time, each as its own job on its worker queue.

Stages marked stub=True are placeholders until their milestone (see PLAN.md);
the runner records them as "stub" so timings never pretend work happened.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from farq.domain.casefile import (
    Artifact,
    CaseFile,
    Evidence,
    Indicates,
    SourceType,
    Strength,
)
from farq.storage.media import MediaStore
from farq.storage.repo import CaseRepository


@dataclass(frozen=True)
class StageContext:
    repo: CaseRepository
    media: MediaStore
    workdir: Path  # empty temporary folder, deleted when the stage ends


@dataclass
class StageOutput:
    evidence: list[Evidence] = field(default_factory=list)
    artifacts: list[Artifact] = field(default_factory=list)


StageFn = Callable[[CaseFile, StageContext], StageOutput]


@dataclass(frozen=True)
class Stage:
    name: str
    queue: str  # io, cpu or gpu
    run: StageFn
    stub: bool = False


def nothing_yet(case: CaseFile, ctx: StageContext) -> StageOutput:
    return StageOutput()


def lookup_known_fake(case: CaseFile, ctx: StageContext) -> StageOutput:
    """Exact-file match against fakes a person already confirmed (sha256).
    Near-duplicate video matching (vpdq) comes later in M2."""
    fake = ctx.repo.find_known_fake(case.media_sha256)
    if fake is None:
        return StageOutput()
    return StageOutput(
        evidence=[
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
    )


DEFAULT_STAGES: list[Stage] = [
    Stage("ingest", "cpu", nothing_yet, stub=True),  # M2: ffprobe, keyframes, 16 kHz audio
    Stage("lookup", "io", lookup_known_fake),
    Stage("ocr", "cpu", nothing_yet, stub=True),  # M2: PaddleOCR on keyframes
    Stage("transcribe", "gpu", nothing_yet, stub=True),  # M2: Whisper with word timings
    Stage("entities", "cpu", nothing_yet, stub=True),  # M2: numbers, UPI IDs, links
    Stage("verify", "io", nothing_yet, stub=True),  # M3: source map, official lists
    Stage("analyse", "gpu", nothing_yet, stub=True),  # M4: audio-visual binding, audio head
]
