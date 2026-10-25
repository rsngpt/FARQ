"""Measure the lower-face vs upper-face change ratio on real videos, against their
originals, to set layer 2's thresholds from data. Runs in the container:

    docker compose run --rm --no-deps -v "${PWD}\\samples:/app/samples:ro" \\
        -v "${PWD}\\scripts:/app/scripts:ro" worker-gpu python scripts/measure_lipsync.py

Each pair is (label, video, its original, seconds into the original where it starts).
"""

import numpy as np

from farq.media.ffmpeg import read_frames
from farq.settings import get_settings
from farq.sourcemap.original import ORIGINAL_FPS, QUERY_FPS, analyse_segment, get_face_finder

LIB, TEST, DEMO = "samples/library", "samples/testset", "samples/demo"
PAIRS = [
    ("genuine copy", f"{LIB}/lib-01-intro.mp4", f"{LIB}/lib-01-intro.mp4"),
    ("genuine copy", f"{LIB}/lib-03-saving.mp4", f"{LIB}/lib-03-saving.mp4"),
    ("genuine squeezed", f"{TEST}/squeezed-lib-01-intro.mp4", f"{LIB}/lib-01-intro.mp4"),
    ("genuine squeezed", f"{TEST}/squeezed-lib-02-upi.mp4", f"{LIB}/lib-02-upi.mp4"),
    ("genuine squeezed", f"{TEST}/squeezed-lib-03-saving.mp4", f"{LIB}/lib-03-saving.mp4"),
    ("genuine squeezed", f"{TEST}/squeezed-lib-04-hometown.mp4", f"{LIB}/lib-04-hometown.mp4"),
    (
        "stitch squeezed",
        f"{TEST}/squeezed-stitched-lib-01-intro-voice-lib-02-upi.mp4",
        f"{LIB}/lib-01-intro.mp4",
    ),  # fmt: skip
    ("LIP-SYNC", f"{DEMO}/lipsync-intro-upi.mp4", f"{LIB}/lib-01-intro.mp4"),
    ("LIP-SYNC squeezed", f"{DEMO}/lipsync-intro-upi-squeezed.mp4", f"{LIB}/lib-01-intro.mp4"),
]
SPAN, SIZE, LEAD = 15.0, (640, 360), 0.5

finder = get_face_finder(get_settings().face_model_path)
for label, video, original in PAIRS:
    q = read_frames(video, start=0, duration=SPAN, fps=QUERY_FPS, size=SIZE, timeout=120)
    o = read_frames(original, start=0, duration=SPAN + LEAD, fps=ORIGINAL_FPS, size=SIZE,
                    timeout=120)  # fmt: skip
    # The test videos start at 0 s of their originals; no lead-in available at 0.
    r = analyse_segment({"start": 0.0, "end": SPAN, "clip_start": 0.0}, q, o, finder,
                        lead_in_s=0.0)  # fmt: skip
    ratios = [s[1] for s in r["samples"]]
    name = video.split("/")[-1]
    print(f"{label:<18} median {np.median(ratios):5.2f}  min {min(ratios):5.2f}  "
          f"max {max(ratios):5.2f}  faces {r['faces_found']:2}  {name}")  # fmt: skip
