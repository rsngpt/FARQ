"""Text clean-up shared by OCR, transcripts and entity extraction."""

import re
import unicodedata

# OCR and speech-to-text sometimes write Devanagari digits (४० for 40).
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Unicode NFC, ASCII digits, single spaces."""
    text = unicodedata.normalize("NFC", text).translate(_DEVANAGARI_DIGITS)
    return _SPACES.sub(" ", text).strip()


def compare_key(text: str) -> str:
    """Loose form for spotting the same text twice: no case, no spaces."""
    return normalise(text).casefold().replace(" ", "")
