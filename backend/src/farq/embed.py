"""Phrase embeddings with BGE-M3 (BAAI's official ONNX export), on CPU.

An embedding is a list of 1024 numbers standing for a phrase's meaning;
phrases that mean the same land close together, across Hindi and English.
Measured in the container on four test phrases (24 Oct): the pitch's returns
promise vs the same promise reworded in Hindi 0.88, vs in English 0.82, vs an
unrelated sentence 0.31 (cosine similarity).

Runs on onnxruntime and tokenizers, which faster-whisper already installs, so
no PyTorch is needed.
"""

import base64
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np

REPO = "BAAI/bge-m3"
MAX_TOKENS = 512


class Embedder(Protocol):
    name: str
    version: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


class BgeM3Embedder:
    name = "BAAI/bge-m3 (ONNX)"

    def __init__(self, model_dir: Path, revision: str, threads: int = 4):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        onnx_dir = model_dir / "onnx"
        if not (onnx_dir / "model.onnx_data").exists():
            from huggingface_hub import snapshot_download

            # Plain files, not cache symlinks: onnxruntime refuses a weights
            # file that resolves outside the model's folder.
            snapshot_download(REPO, revision=revision, allow_patterns=["onnx/*"],
                              local_dir=model_dir)  # fmt: skip
        self.version = f"{revision[:12]} onnxruntime {ort.__version__}"
        self._tokenizer = Tokenizer.from_file(str(onnx_dir / "tokenizer.json"))
        self._tokenizer.enable_truncation(MAX_TOKENS)
        self._tokenizer.enable_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = ort.InferenceSession(
            str(onnx_dir / "model.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def embed(self, texts: list[str], batch: int = 16) -> np.ndarray:
        """(len(texts), 1024) unit-length vectors."""
        out = []
        for i in range(0, len(texts), batch):
            enc = self._tokenizer.encode_batch(texts[i : i + batch])
            feed = {
                "input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64),
            }
            out.append(self._session.run(["sentence_embedding"], feed)[0])
        if not out:
            return np.zeros((0, 1024), dtype=np.float32)
        vectors = np.concatenate(out).astype(np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


@lru_cache
def get_embedder(model_dir: Path, revision: str, threads: int) -> Embedder:
    return BgeM3Embedder(model_dir, revision, threads)


def pack(vector: np.ndarray) -> str:
    """Store a vector compactly (float16, base64): about 2.7 KB instead of 20 KB."""
    return base64.b64encode(vector.astype(np.float16).tobytes()).decode("ascii")


def unpack(text: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(text), dtype=np.float16).astype(np.float32)
