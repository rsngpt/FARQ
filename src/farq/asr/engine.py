"""Speech-to-text engine: Whisper large-v3-turbo through faster-whisper
(CTranslate2), from weights we converted ourselves."""

import json
import os
import wave
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np


def read_wav_16k(path: Path) -> np.ndarray:
    """Samples from ingest's 16 kHz mono 16-bit WAV, as floats in [-1, 1].

    Passing samples (not a path) keeps faster-whisper from decoding the file
    with PyAV: faster-whisper 1.2.1 passes an option newer PyAV rejects."""
    with wave.open(str(path)) as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            raise ValueError(f"{path.name} is not 16 kHz mono 16-bit audio")
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    return pcm.astype(np.float32) / 32768.0


def _use_pip_cuda_libraries_on_windows() -> None:
    """On a Windows dev laptop, let CTranslate2 find the cuBLAS/cuDNN DLLs from
    the `gpu` extra (pip's nvidia-* packages). The Linux GPU image sets
    LD_LIBRARY_PATH instead, so this does nothing there."""
    if os.name != "nt":
        return
    try:
        import nvidia  # namespace package from nvidia-cublas-cu12 / nvidia-cudnn-cu12
    except ImportError:
        return
    for root in nvidia.__path__:
        for bin_dir in Path(root).glob("*/bin"):
            os.add_dll_directory(str(bin_dir))
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"


class AsrEngine(Protocol):
    name: str
    version: str

    def transcribe(self, wav: Path) -> dict[str, Any]: ...


class WhisperEngine:
    name = "whisper-large-v3-turbo"

    def __init__(self, model_dir: Path, gpu_compute_type: str, beam_size: int):
        if not (model_dir / "PROVENANCE.json").exists():
            raise FileNotFoundError(
                f"No converted Whisper model in {model_dir}; run scripts/convert_whisper.py"
            )
        _use_pip_cuda_libraries_on_windows()
        import ctranslate2  # heavy imports; only where speech-to-text runs
        import faster_whisper

        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        compute_type = gpu_compute_type if device == "cuda" else "int8"
        revision = json.loads((model_dir / "PROVENANCE.json").read_text())["source_revision"]
        # Which weights, in which form, on which device: enough to reproduce a result.
        self.version = (
            f"openai@{revision[:12]} {compute_type} {device} "
            f"faster-whisper {faster_whisper.__version__}"
        )
        self.beam_size = beam_size
        self._model = faster_whisper.WhisperModel(
            str(model_dir), device=device, compute_type=compute_type
        )

    def transcribe(self, wav: Path) -> dict[str, Any]:
        segments, info = self._model.transcribe(
            read_wav_16k(wav),
            beam_size=self.beam_size,
            word_timestamps=True,
            vad_filter=True,  # Silero VAD: skip silence
            # Each segment stands alone, so one misheard phrase isn't repeated
            # into the next (a known Whisper failure on long audio).
            condition_on_previous_text=False,
        )
        segs = [
            {
                "start": round(s.start, 2),
                "end": round(s.end, 2),
                "text": s.text.strip(),
                "words": [
                    {
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                        "word": w.word.strip(),
                        "p": round(w.probability, 3),
                    }
                    for w in (s.words or [])
                ],
            }
            for s in segments  # a generator: transcription happens here
        ]
        return {
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration_s": round(info.duration, 2),
            "speech_s": round(info.duration_after_vad, 2),
            "text": " ".join(s["text"] for s in segs),
            "segments": segs,
        }


@lru_cache
def get_asr_engine(model_dir: Path, gpu_compute_type: str, beam_size: int) -> AsrEngine:
    """One model per worker process. The GPU worker runs one job at a time,
    so only this model is on the GPU while it transcribes."""
    return WhisperEngine(model_dir, gpu_compute_type, beam_size)
