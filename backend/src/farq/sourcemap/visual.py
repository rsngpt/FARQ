"""Visual source map: which library clip, and which moment of it, each part of a
forwarded video's picture came from."""

from typing import Any

import numpy as np

from farq.library import LibraryClip
from farq.media import pdq

# A segment continues while the offset (library time - video time) stays within
# this many seconds of where it started; a jump means a cut to other footage.
OFFSET_TOLERANCE_S = 0.75
# Shorter matches are ignored: two frames at 2 per second.
MIN_SEGMENT_FRAMES = 2


def visual_map(
    frames: list[dict[str, Any]],
    clips: list[LibraryClip],
    *,
    max_distance: int = pdq.MATCH_DISTANCE,
    min_quality: int = pdq.MIN_QUALITY,
) -> list[dict[str, Any]]:
    """Timeline of the video, in order: matched segments (with the clip and the
    matching span in it) and "no source found" gaps."""
    if not frames:
        return []
    step = frames[1]["t"] - frames[0]["t"] if len(frames) > 1 else 0.5
    usable = [f for f in frames if f["q"] >= min_quality]
    query = pdq.to_bits([f["pdq"] for f in usable])

    # Every library frame within reach of every usable query frame.
    candidates: list[list[tuple[int, float, int]]] = [[] for _ in usable]  # (clip, t, dist)
    for ci, clip in enumerate(clips):
        lib_frames = [f for f in clip.fingerprints["frames"] if f["q"] >= min_quality]
        if not lib_frames:
            continue
        dist = pdq.distances(query, pdq.to_bits([f["pdq"] for f in lib_frames]))
        for qi, li in zip(*np.nonzero(dist <= max_distance), strict=True):
            candidates[qi].append((ci, lib_frames[li]["t"], int(dist[qi, li])))

    # Walk the video in order, preferring the candidate that continues the
    # current segment (same clip, same offset), else the closest match.
    runs: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for f, options in zip(usable, candidates, strict=True):
        pick = None
        if current is not None:
            continuing = [
                o for o in options
                if o[0] == current["clip"]
                and abs((o[1] - f["t"]) - current["offset"]) <= OFFSET_TOLERANCE_S
            ]  # fmt: skip
            pick = min(continuing, key=lambda o: o[2], default=None)
        if pick is None and options:
            pick = min(options, key=lambda o: (o[2], o[1]))
            current = None
        if pick is None:
            current = None
            continue
        if current is None:
            current = {"clip": pick[0], "offset": pick[1] - f["t"], "frames": []}
            runs.append(current)
        current["frames"].append((f["t"], pick[1], pick[2]))

    timeline: list[dict[str, Any]] = []
    for run in (r for r in runs if len(r["frames"]) >= MIN_SEGMENT_FRAMES):
        clip = clips[run["clip"]]
        ts = [t for t, _, _ in run["frames"]]
        lib_ts = [lt for _, lt, _ in run["frames"]]
        timeline.append(
            {
                "start": round(ts[0], 2),
                "end": round(ts[-1] + step, 2),
                "clip_id": str(clip.id),
                "person": clip.person,
                "title": clip.title,
                "clip_start": round(lib_ts[0], 2),
                "clip_end": round(lib_ts[-1] + step, 2),
                "mean_distance": round(float(np.mean([d for _, _, d in run["frames"]])), 1),
                "frames": len(ts),
            }
        )
    return with_gaps(timeline, start=frames[0]["t"], end=frames[-1]["t"] + step)


def with_gaps(matched: list[dict[str, Any]], *, start: float, end: float) -> list[dict[str, Any]]:
    """Insert "no source found" entries for the parts of the video that matched nothing."""
    out: list[dict[str, Any]] = []
    cursor = start
    for seg in sorted(matched, key=lambda s: s["start"]):
        if seg["start"] - cursor > 0.01:
            out.append({"start": round(cursor, 2), "end": seg["start"], "clip_id": None})
        out.append(seg)
        cursor = max(cursor, seg["end"])
    if end - cursor > 0.01:
        out.append({"start": round(cursor, 2), "end": round(end, 2), "clip_id": None})
    return out
