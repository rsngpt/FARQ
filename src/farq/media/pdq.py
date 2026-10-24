"""PDQ perceptual hashes (Meta's pdqhash): a 256-bit fingerprint per frame that
stays close when a video is re-compressed, resized or slightly cropped.

Two frames are "the same picture" when their hashes differ in at most
MATCH_DISTANCE of 256 bits (Meta's suggested threshold for PDQ is 31).
A lip-sync edit changes only the mouth, a small part of the frame, so the
fingerprint of an altered frame stays close to the original's.
"""

from pathlib import Path

import numpy as np
from PIL import Image

MATCH_DISTANCE = 31
# PDQ's own quality score (0-100); flat or blank frames score low and match
# anything, so they are left out of matching.
MIN_QUALITY = 50


def hash_image(path: Path) -> tuple[str, int]:
    """(64-character hex hash, quality 0-100) for one image file."""
    import pdqhash  # compiled extension; only where frames are hashed

    with Image.open(path) as img:
        rgb = np.asarray(img.convert("RGB"))
    bits, quality = pdqhash.compute(rgb)
    return np.packbits(bits.astype(np.uint8)).tobytes().hex(), int(quality)


def to_bits(hex_hashes: list[str]) -> np.ndarray:
    """Hex hashes -> (n, 256) array of 0/1 bits, for fast distance maths."""
    if not hex_hashes:
        return np.zeros((0, 256), dtype=np.uint8)
    packed = np.frombuffer(b"".join(bytes.fromhex(h) for h in hex_hashes), dtype=np.uint8)
    return np.unpackbits(packed.reshape(len(hex_hashes), 32), axis=1)


def distances(query: np.ndarray, library: np.ndarray) -> np.ndarray:
    """Hamming distance between every query hash and every library hash: (q, l)."""
    if len(query) == 0 or len(library) == 0:
        return np.zeros((len(query), len(library)), dtype=np.int32)
    return (query[:, None, :] != library[None, :, :]).sum(axis=2, dtype=np.int32)
