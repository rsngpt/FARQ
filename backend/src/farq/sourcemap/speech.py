"""Speech source map: which library recording, and which moment of it, each
phrase of a forwarded video's speech came from.

Exact matching first: runs of the same five words, in order, in a library
transcript. Two Whisper runs on the same audio rarely produce identical text,
so a run may skip a couple of words that differ and continue.
"""

import unicodedata
from typing import Any

import numpy as np

from farq.embed import Embedder, unpack
from farq.library import LibraryClip
from farq.sourcemap.visual import with_gaps
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

    spans = []  # [clip, q_first, q_end, l_first, l_end]
    for r in runs:
        lib = library[r["clip"]]
        # Grow the run outwards past words a five-word lookup couldn't bridge.
        back = _extend(query, lib, r["q_first"], r["l_first"], -1)
        q_end, l_end = r["q_last"] + SHINGLE - 1, r["l_last"] + SHINGLE - 1
        forward = _extend(query, lib, q_end, l_end, +1)
        spans.append([r["clip"], r["q_first"] - back, q_end + forward,
                      r["l_first"] - back, l_end + forward])  # fmt: skip

    # Pieces of one phrase, split by differing words, can grow into the same
    # span; merge overlapping spans from the same clip into one.
    merged: list[list[int]] = []
    for span in sorted(spans):
        last = merged[-1] if merged else None
        if last and last[0] == span[0] and span[1] <= last[2] + 1:
            last[2], last[4] = max(last[2], span[2]), max(last[4], span[4])
            last[3] = min(last[3], span[3])
        else:
            merged.append(span)

    out = []
    for ci, q_first, q_end, l_first, l_end in merged:
        clip, lib = clips[ci], library[ci]
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


def phrase_windows(words: list[dict[str, Any]], size: int, stride: int) -> list[dict[str, Any]]:
    """Overlapping windows of `size` words, every `stride` words; the last window
    always reaches the end so no speech is left out."""
    if not words:
        return []
    starts = list(range(0, max(1, len(words) - size + 1), stride))
    if starts[-1] + size < len(words):
        starts.append(len(words) - size)
    return [
        {
            "start": words[i]["start"],
            "end": words[min(i + size, len(words)) - 1]["end"],
            "text": " ".join(w["w"] for w in words[i : i + size]),
        }
        for i in starts
    ]


def similar_matches(
    query: list[dict[str, Any]],
    clips: list[LibraryClip],
    embedder: Embedder,
    *,
    covered: list[dict[str, Any]],
    size: int,
    stride: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Phrases whose meaning is close to a library phrase (BGE-M3), for speech the
    exact matcher didn't place: rewording, transcription errors, translation."""

    def mostly_covered(w: dict[str, Any]) -> bool:
        span = w["end"] - w["start"] or 1e-6
        overlap = sum(max(0.0, min(w["end"], c["end"]) - max(w["start"], c["start"]))
                      for c in covered)  # fmt: skip
        return overlap / span > 0.5

    windows = [w for w in phrase_windows(query, size, stride) if not mostly_covered(w)]
    library = [(ci, p) for ci, c in enumerate(clips) for p in (c.phrases or [])]
    if not windows or not library:
        return []

    q = embedder.embed([w["text"] for w in windows])
    lib = np.stack([unpack(p["vec"]) for _, p in library])
    sims = q @ lib.T

    segments: list[dict[str, Any]] = []
    for w, row in zip(windows, sims, strict=True):
        best = int(row.argmax())
        if row[best] < min_similarity:
            continue
        ci, phrase = library[best]
        clip, sim = clips[ci], float(row[best])
        last = segments[-1] if segments else None
        if (last and last["clip_id"] == str(clip.id) and w["start"] <= last["end"]
                and phrase["start"] >= last["clip_start"]):  # fmt: skip
            last.update(end=max(last["end"], w["end"]),
                        clip_end=max(last["clip_end"], phrase["end"]),
                        similarity=round(max(last["similarity"], sim), 3))  # fmt: skip
            continue
        segments.append(
            {
                "start": w["start"],
                "end": w["end"],
                "clip_id": str(clip.id),
                "person": clip.person,
                "title": clip.title,
                "clip_start": phrase["start"],
                "clip_end": phrase["end"],
                "method": "similar",
                "similarity": round(sim, 3),
                "text": w["text"],
            }
        )
    return segments


def speech_map(
    transcript: dict[str, Any] | None,
    clips: list[LibraryClip],
    embedder: Embedder | None,
    *,
    size: int,
    stride: int,
    min_similarity: float,
) -> list[dict[str, Any]]:
    """Timeline of the speech: exact matches, then similar phrases, then
    "no source found" for the spoken parts that matched nothing."""
    query = words_of(transcript)
    if not query:
        return []
    found = exact_matches(query, clips)
    if embedder is not None:
        found += similar_matches(query, clips, embedder, covered=found, size=size,
                                 stride=stride, min_similarity=min_similarity)  # fmt: skip
    return with_gaps(sorted(found, key=lambda s: s["start"]),
                     start=query[0]["start"], end=query[-1]["end"])  # fmt: skip
