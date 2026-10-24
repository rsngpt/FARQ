"""OCR engine: PaddleOCR (PP-OCRv5) on CPU.

Settings measured on synthetic 1280x720 frames in the Linux container
(12 cores): the mobile text detector with frames shrunk to a 736 px long side
took 0.9-2.2 s per frame and read whole lines correctly; the server detector at
full size took 24-57 s. The Devanagari recognition model reads both Hindi and
English, so one pass covers both.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

DET_MODEL = "PP-OCRv5_mobile_det"
REC_MODEL = "devanagari_PP-OCRv5_mobile_rec"


@dataclass(frozen=True)
class TextLine:
    text: str
    score: float
    box: list[list[int]]  # four corner points, in frame pixels


class OcrEngine(Protocol):
    name: str
    version: str

    def read(self, images: list[Path]) -> list[list[TextLine]]: ...


class PaddleOcrEngine:
    name = f"{DET_MODEL}+{REC_MODEL}"

    def __init__(self, det_side: int):
        from paddleocr import PaddleOCR, __version__  # heavy import; only where OCR runs

        self.version = f"paddleocr {__version__}"
        self._ocr = PaddleOCR(
            text_detection_model_name=DET_MODEL,
            text_recognition_model_name=REC_MODEL,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_det_limit_type="max",
            text_det_limit_side_len=det_side,
            cpu_threads=os.cpu_count() or 4,
            # PaddlePaddle 3.3.1's oneDNN path crashes on these models
            # ("ConvertPirAttribute2RuntimeAttribute not support"), on Windows and Linux.
            enable_mkldnn=False,
        )

    def read(self, images: list[Path]) -> list[list[TextLine]]:
        results = self._ocr.predict([str(p) for p in images])
        return [
            [
                TextLine(text=text, score=float(score), box=[[int(x), int(y)] for x, y in poly])
                for text, score, poly in zip(
                    res["rec_texts"], res["rec_scores"], res["rec_polys"], strict=True
                )
            ]
            for res in results
        ]


@lru_cache
def get_ocr_engine(det_side: int) -> OcrEngine:
    """One engine per worker process; loading the models takes a few seconds."""
    return PaddleOcrEngine(det_side)
