"""Latency numbers for the live demo panel, measured from real stage runs."""

import math
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from farq.api.deps import RepoDep

router = APIRouter(prefix="/metrics", tags=["metrics"])

TARGETS_MS = {"known_fake": 10_000, "new_video": 60_000}


class LatencySummary(BaseModel):
    count: int
    p50_ms: int
    p95_ms: int
    max_ms: int


class LatencyReport(BaseModel):
    cases: int
    targets_ms: dict[str, int]
    end_to_end: dict[str, LatencySummary | None]
    stages: dict[str, LatencySummary]


@router.get("/latency")
def latency(repo: RepoDep, last: Annotated[int, Query(ge=1, le=500)] = 50) -> LatencyReport:
    """Upload to verdict, split by known fakes vs new videos, plus per-stage timings."""
    cases = repo.recent_decided(last)
    end_to_end: dict[str, list[float]] = {"known_fake": [], "new_video": []}
    per_stage: dict[str, list[float]] = {}
    for case in cases:
        if case.decision is not None:
            kind = (
                "known_fake"
                if any(e.type == "known_fake_hash" for e in case.evidence)
                else "new_video"
            )
            elapsed = (case.decision.decided_at - case.created_at).total_seconds() * 1000
            end_to_end[kind].append(elapsed)
        for t in case.timings:
            per_stage.setdefault(t.stage, []).append(t.duration_ms)
    return LatencyReport(
        cases=len(cases),
        targets_ms=TARGETS_MS,
        end_to_end={kind: _summarise(values) for kind, values in end_to_end.items()},
        stages={stage: s for stage, values in per_stage.items() if (s := _summarise(values))},
    )


def _summarise(values: list[float]) -> LatencySummary | None:
    if not values:
        return None
    ordered = sorted(values)

    def percentile(p: float) -> int:
        # Nearest-rank percentile: an actual measured value, not an interpolation.
        return round(ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)])

    return LatencySummary(
        count=len(ordered), p50_ms=percentile(50), p95_ms=percentile(95), max_ms=round(ordered[-1])
    )
