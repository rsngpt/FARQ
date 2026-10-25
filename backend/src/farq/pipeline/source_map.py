"""Source map stage: where each part of the video's picture and speech came
from in the library of genuine clips; for picture matches, find the original
and show what changed; then turn that into evidence."""

import logging
from pathlib import PurePath
from typing import Any

from farq.domain.casefile import Artifact, CaseFile
from farq.embed import Embedder, get_embedder
from farq.library import LibraryClip, load_clips
from farq.media import ffmpeg
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings
from farq.sourcemap.evidence import known_fake_evidence, source_evidence
from farq.sourcemap.original import (
    MAX_SPAN_S,
    ORIGINAL_FPS,
    QUERY_FPS,
    analyse_segment,
    compare_speech,
    get_face_finder,
)
from farq.sourcemap.speech import speech_map
from farq.sourcemap.visual import visual_map

MAX_ORIGINALS = 2  # longest matched segments compared with their originals
ANALYSIS_WIDTH = 640

logger = logging.getLogger(__name__)


class _NoFaces:
    """Stand-in when MediaPipe can't start: no faces, so no mouth reading."""

    name = "unavailable"
    version = "-"

    def regions(self, rgb):
        return None


def source_map(case: CaseFile, ctx: StageContext, embedder: Embedder | None = None) -> StageOutput:
    fingerprints = case.artifact("fingerprints")
    transcript = case.artifact("transcript")
    if fingerprints is None and transcript is None:
        return StageOutput()  # screenshot: nothing to map
    s = get_settings()
    all_clips = load_clips(ctx.repo.session)
    fakes = [c for c in all_clips if c.is_known_fake]
    clips = [c for c in all_clips if not c.is_known_fake]
    if embedder is None and transcript is not None and any(c.phrases for c in clips):
        embedder = get_embedder(s.bge_m3_dir, s.bge_m3_revision, s.embed_threads)

    data: dict[str, Any] = {
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
    data["originals"] = _find_originals(case, ctx, data["visual"], clips, transcript)
    fake_map = visual_map(fingerprints.data["frames"], fakes) if fingerprints and fakes else []
    data["known_fakes"] = [seg for seg in fake_map if seg.get("clip_id")]
    sources = {str(c.id): c.source for c in fakes}
    return StageOutput(
        evidence=known_fake_evidence(data["known_fakes"], sources) + source_evidence(data),
        artifacts=[
            Artifact(
                stage="source_map",
                kind="source_map",
                data=data,
                model_name=embedder.name if embedder else None,
                model_version=embedder.version if embedder else None,
            )
        ],
    )


def _find_originals(
    case: CaseFile,
    ctx: StageContext,
    visual: list[dict[str, Any]],
    clips: list[LibraryClip],
    transcript: Artifact | None,
) -> list[dict[str, Any]]:
    matched = sorted((v for v in visual if v.get("clip_id")),
                     key=lambda v: v["end"] - v["start"], reverse=True)[:MAX_ORIGINALS]  # fmt: skip
    if not matched:
        return []
    s = get_settings()
    by_id = {str(c.id): c for c in clips}
    video = ctx.workdir / f"video{PurePath(case.media_key).suffix}"
    ctx.media.download(case.media_key, video)
    try:
        finder = get_face_finder(s.face_model_path)
    except Exception:
        # The source map and "not recorded together" still stand without the
        # mouth check; the mouth reading is then "unknown".
        logger.exception("face finder unavailable; skipping the mouth check")
        finder = _NoFaces()

    results = []
    for seg in matched:
        clip = by_id[seg["clip_id"]]
        if not clip.media_key:
            continue
        original = ctx.workdir / f"original-{clip.id}{PurePath(clip.media_key).suffix}"
        if not original.exists():
            ctx.media.download(clip.media_key, original)
        info = ffmpeg.probe(original, s.ffmpeg_timeout_s)
        width = min(ANALYSIS_WIDTH, info.video["width"])
        size = (width, round(info.video["height"] * width / info.video["width"] / 2) * 2)
        span = min(seg["end"] - seg["start"], MAX_SPAN_S)
        lead_in = min(0.5, seg["clip_start"])
        query_frames = ffmpeg.read_frames(
            video, start=seg["start"], duration=span, fps=QUERY_FPS, size=size,
            timeout=s.ffmpeg_timeout_s,
        )  # fmt: skip
        original_frames = ffmpeg.read_frames(
            original, start=seg["clip_start"] - lead_in, duration=span + 2 * lead_in,
            fps=ORIGINAL_FPS, size=size, timeout=s.ffmpeg_timeout_s,
        )  # fmt: skip
        comp = analyse_segment(seg, query_frames, original_frames, finder, lead_in_s=lead_in)
        comp["segment"] = seg
        comp["speech"] = compare_speech(
            transcript.data if transcript else None, clip.transcript,
            video_span=(seg["start"], seg["start"] + span),
            original_start=seg["start"] + comp["offset_s"],
        )  # fmt: skip
        results.append(comp)
    return results
