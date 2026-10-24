"""Source map stage: where each part of the video's picture and speech came
from in the library of genuine clips."""

from farq.domain.casefile import Artifact, CaseFile
from farq.embed import Embedder, get_embedder
from farq.library import load_clips
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings
from farq.sourcemap.speech import speech_map
from farq.sourcemap.visual import visual_map


def source_map(case: CaseFile, ctx: StageContext, embedder: Embedder | None = None) -> StageOutput:
    fingerprints = case.artifact("fingerprints")
    transcript = case.artifact("transcript")
    if fingerprints is None and transcript is None:
        return StageOutput()  # screenshot: nothing to map
    s = get_settings()
    clips = load_clips(ctx.repo.session)
    if embedder is None and transcript is not None and any(c.phrases for c in clips):
        embedder = get_embedder(s.bge_m3_dir, s.bge_m3_revision, s.embed_threads)

    data = {
        "library_clips": len(clips),
        "visual": visual_map(fingerprints.data["frames"], clips) if fingerprints else [],
        "speech": speech_map(
            transcript.data if transcript else None,
            clips,
            embedder,
            size=s.phrase_window_words,
            stride=s.phrase_stride_words,
            min_similarity=s.similar_phrase_min,
        ),  # fmt: skip
    }
    return StageOutput(
        artifacts=[
            Artifact(
                stage="source_map",
                kind="source_map",
                data=data,
                model_name=embedder.name if embedder else None,
                model_version=embedder.version if embedder else None,
            )
        ]
    )
