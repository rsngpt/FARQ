"""Source map stage: where each part of the video's picture (and, next, its
speech) came from in the library of genuine clips."""

from farq.domain.casefile import Artifact, CaseFile
from farq.library import load_clips
from farq.pipeline.stages import StageContext, StageOutput
from farq.sourcemap.visual import visual_map


def source_map(case: CaseFile, ctx: StageContext) -> StageOutput:
    fingerprints = case.artifact("fingerprints")
    if fingerprints is None:
        return StageOutput()  # voice note or screenshot: no moving picture to map
    clips = load_clips(ctx.repo.session)
    visual = visual_map(fingerprints.data["frames"], clips)
    return StageOutput(
        artifacts=[
            Artifact(
                stage="source_map",
                kind="source_map",
                data={"library_clips": len(clips), "visual": visual},
            )
        ]
    )
