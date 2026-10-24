"""Analyse stage: the voice-and-body check (layer 3), calibrated against the
genuine library clips of the person the picture matched."""

from pathlib import PurePath

from farq.binding import calibrated, measure_clip
from farq.domain.casefile import (
    Artifact,
    CaseFile,
    Evidence,
    Indicates,
    Level,
    SourceType,
    Strength,
)
from farq.library import load_clips
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings
from farq.sourcemap.original import get_face_finder


def analyse(case: CaseFile, ctx: StageContext) -> StageOutput:
    source_map = case.artifact("source_map")
    audio = case.artifact("audio_16k")
    if source_map is None or audio is None or case.artifact("fingerprints") is None:
        return StageOutput()  # needs a video with sound
    matched = [v for v in source_map.data.get("visual", []) if v.get("clip_id")]
    if not matched:
        return StageOutput(artifacts=[_record({"status": "no_person_matched"})])
    person = max(matched, key=lambda v: v["end"] - v["start"])["person"]
    genuine = [c.binding_score for c in load_clips(ctx.repo.session)
               if c.person == person and c.binding_score is not None]  # fmt: skip

    s = get_settings()
    video = ctx.workdir / f"video{PurePath(case.media_key).suffix}"
    wav = ctx.workdir / "audio16k.wav"
    ctx.media.download(case.media_key, video)
    ctx.media.download(audio.storage_key, wav)
    finder = get_face_finder(s.face_model_path)
    score = measure_clip(video, wav, finder, timeout=s.ffmpeg_timeout_s)
    result = calibrated(score, genuine) if score is not None else None

    record = {
        "status": "measured",
        "person": person,
        "score": score,  # internal only; never put in evidence or the reply
        "genuine_clips": len(genuine),
        "level": result[0] if result else "unknown",
    }
    evidence = []
    if result and result[0] in ("high", "medium"):
        level, explanation = result
        evidence.append(
            Evidence(
                stage="analyse",
                type="voice_body_mismatch",
                source_type=SourceType.MODEL,
                strength=Strength.STRONG if level == "high" else Strength.WEAK,
                indicates=Indicates.SCAM,
                level=Level(level),
                reason=f"Their head and eyebrow movements don't match this voice ({explanation}).",
                model_name="voice-body sync v1 (MediaPipe + librosa pYIN)",
                model_version=finder.version,
                details={k: v for k, v in record.items() if k != "score"},
            )
        )
    return StageOutput(evidence=evidence, artifacts=[_record(record)])


def _record(data: dict) -> Artifact:
    return Artifact(stage="analyse", kind="binding", data=data)
