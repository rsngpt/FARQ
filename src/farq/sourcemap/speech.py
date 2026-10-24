"""Speech source map: which library recording, and which moment of it, each
phrase of a forwarded video's speech came from.

Exact matching first: runs of the same five words, in order, in a library
transcript. Two Whisper runs on the same audio rarely produce identical text,
so a run may skip a couple of words that differ and continue.
"""

import unicodedata
from typing import Any

from farq.library import LibraryClip
from farq.text import normalise

SHINGLE = 5  # words per lookup
MAX_SKIP = 2  # words a run may skip on either side and still continue
MIN_RUN_WORDS = 6  # shorter matches are coincidence, not a source

KEEP = set("%@.")  # meaningful in numbers, UPI IDs and links


def _clean(word: str) -> str:
    """Drop punctuation and symbols (। , ! ?), keep letters, digits and Hindi
    vowel signs. (A regex \\w would drop the vowel signs: "है" -> "ह".)"""
    kept = "".join(
        c for c in normalise(word).casefold()
        if c in KEEP or unicodedata.category(c)[0] not in "PSZ"
    )  # fmt: skip
    return kept.strip(".")


def words_of(transcript: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Flat list of {"w": cleaned word, "start", "end"} from a transcript."""
    if not transcript:
        return []
    out = []
    for segment in transcript.get("segments", []):
        for w in segment.get("words", []):
            if token := _clean(w["word"]):
                out.append({"w": token, "start": w["start"], "end": w["end"]})
    return out


def _extend(
    query: list[dict[str, Any]], lib: list[dict[str, Any]], qi: int, lj: int, step: int
) -> int:
    """How many more words, going `step` (-1 back, +1 forward) from aligned
    positions, still line up, allowing up to MAX_SKIP differing words in a row."""
    best, misses, k = 0, 0, 1
    while 0 <= qi + step * k < len(query) and 0 <= lj + step * k < len(lib):
        if query[qi + step * k]["w"] == lib[lj + step * k]["w"]:
            best, misses = k, 0
        else:
            misses += 1
            if misses > MAX_SKIP:
                break
        k += 1
    return best


def exact_matches(query: list[dict[str, Any]], clips: list[LibraryClip]) -> list[dict[str, Any]]:
    """Runs of query words found, in order, in a library transcript."""
    library = [words_of(c.transcript) for c in clips]
    index: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    for ci, words in enumerate(library):
        for j in range(len(words) - SHINGLE + 1):
            index.setdefault(tuple(w["w"] for w in words[j : j + SHINGLE]), []).append((ci, j))

    hits = []  # (query position, clip, library position)
    for i in range(len(query) - SHINGLE + 1):
        for ci, j in index.get(tuple(w["w"] for w in query[i : i + SHINGLE]), []):
            hits.append((i, ci, j))

    runs: list[dict[str, Any]] = []
    for i, ci, j in sorted(hits):
        run = next(
            (r for r in runs
             if r["clip"] == ci
             and 0 < i - r["q_last"] <= MAX_SKIP + 1
             and 0 < j - r["l_last"] <= MAX_SKIP + 1),
            None,
        )  # fmt: skip
        if run is None:
            runs.append({"clip": ci, "q_first": i, "q_last": i, "l_first": j, "l_last": j})
        else:
            run["q_last"], run["l_last"] = i, j

    out = []
    for r in runs:
        clip, lib = clips[r["clip"]], library[r["clip"]]
        # Grow the run outwards past words a five-word lookup couldn't bridge.
        back = _extend(query, lib, r["q_first"], r["l_first"], -1)
        q_first, l_first = r["q_first"] - back, r["l_first"] - back
        q_end, l_end = r["q_last"] + SHINGLE - 1, r["l_last"] + SHINGLE - 1
        forward = _extend(query, lib, q_end, l_end, +1)
        q_end, l_end = q_end + forward, l_end + forward
        if q_end - q_first + 1 < MIN_RUN_WORDS:
            continue
        out.append(
            {
                "start": query[q_first]["start"],
                "end": query[q_end]["end"],
                "clip_id": str(clip.id),
                "person": clip.person,
                "title": clip.title,
                "clip_start": lib[l_first]["start"],
                "clip_end": lib[l_end]["end"],
                "method": "exact",
                "words": q_end - q_first + 1,
                "text": " ".join(w["w"] for w in query[q_first : q_end + 1]),
            }
        )
    return sorted(out, key=lambda s: s["start"])
