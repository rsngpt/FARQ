"""Transcribe stage: speech-to-text with a timestamp for every word, for the
source map (M3), scam-script matching and spoken entities."""

from farq.asr.engine import AsrEngine, get_asr_engine
from farq.domain.casefile import Artifact, CaseFile
from farq.pipeline.stages import StageContext, StageOutput
from farq.settings import get_settings


def transcribe(case: CaseFile, ctx: StageContext, engine: AsrEngine | None = None) -> StageOutput:
    audio = case.artifact("audio_16k")
    if audio is None or audio.storage_key is None:
        return StageOutput()  # screenshot or silent video: nothing to hear
    settings = get_settings()
    engine = engine or get_asr_engine(
        settings.whisper_model_dir, settings.whisper_gpu_compute_type, settings.whisper_beam_size
    )
    wav = ctx.workdir / "audio16k.wav"
    ctx.media.download(audio.storage_key, wav)
    return StageOutput(
        artifacts=[
            Artifact(
                stage="transcribe",
                kind="transcript",
                data=engine.transcribe(wav),
                model_name=engine.name,
                model_version=engine.version,
            )
        ]
    )
