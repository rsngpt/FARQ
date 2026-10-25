"""M6 test set: build test videos from the team's clips, run each through the
FARQ API like the WhatsApp bot does, and write a results table.

    uv run python scripts/run_testset.py --library samples/library \
        --held-out lib-11-weekend.mp4 lib-12-advice.mp4 [--pitch samples/library/pitch-01-scam.mp4]

Test items (all made locally with FFmpeg; nothing leaves this laptop):
  genuine     held-out clips FARQ has never seen       expected NOT_VERIFIED
  copy        library clips, as-is                     expected NOT_VERIFIED
  stitched    picture of clip A + voice of clip B      expected LIKELY_SCAM
  pitch       picture of clip A + the scam pitch voice expected LIKELY_SCAM
Each item is also run "squeezed": 480p, H.264 CRF 30, AAC 64k, an approximation
of WhatsApp's re-encode (the live rehearsal through WhatsApp is the real test).

Only measured results are written: counts per group, never invented rates.
"""

import argparse
import itertools
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

SQUEEZE = ["-vf", "scale=-2:480", "-c:v", "libx264", "-crf", "30", "-preset", "fast",
           "-c:a", "aac", "-b:a", "64k"]  # fmt: skip
EXPECTED = {"genuine": "NOT_VERIFIED", "copy": "NOT_VERIFIED",
            "stitched": "LIKELY_SCAM", "pitch": "LIKELY_SCAM"}  # fmt: skip
SCAM = {"LIKELY_SCAM", "CONFIRMED_SCAM"}


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def stitch(picture: Path, voice: Path, out: Path, seconds: int = 30) -> None:
    """Picture from one clip with the voice of another (plain stitch, no lip-sync)."""
    ffmpeg(
        "-i", str(picture), "-i", str(voice), "-map", "0:v", "-map", "1:a",
        "-t", str(seconds), "-c:v", "libx264", "-crf", "20", "-c:a", "aac", str(out),
    )  # fmt: skip


def build(args: argparse.Namespace, work: Path) -> list[tuple[str, str, Path]]:
    clips = sorted(p for p in args.library.glob("lib-*.mp4"))
    held_out = [p for p in clips if p.name in set(args.held_out)]
    in_library = [p for p in clips if p not in held_out]
    if len(in_library) < 2:
        sys.exit("Need at least 2 library clips (lib-*.mp4) besides the held-out ones")

    items: list[tuple[str, str, Path]] = []
    items += [("genuine", p.stem, p) for p in held_out]
    items += [("copy", p.stem, p) for p in in_library[: args.max_per_group]]
    pairs = list(itertools.permutations(in_library, 2))[: args.max_per_group]
    for a, b in pairs:
        out = work / f"stitched-{a.stem}-voice-{b.stem}.mp4"
        stitch(a, b, out)
        items.append(("stitched", out.stem, out))
    for pitch in args.pitch:
        for a in in_library[: args.max_per_group]:
            out = work / f"pitch-{a.stem}-voice-{pitch.stem}.mp4"
            stitch(a, pitch, out)
            items.append(("pitch", out.stem, out))

    squeezed = []
    for group, name, path in items:
        out = work / f"squeezed-{name}.mp4"
        ffmpeg("-i", str(path), *SQUEEZE, str(out))
        squeezed.append((group, f"{name} (squeezed)", out))
    return items + squeezed


def run(client: httpx.Client, path: Path, timeout: float) -> tuple[str, str, float]:
    started = time.perf_counter()
    with path.open("rb") as f:
        fields = {
            "media_type": "video",
            "user_ref": "testset",
            "idempotency_key": f"testset-{path.stem}-{time.time_ns()}",
        }
        r = client.post("/cases", files={"file": (path.name, f)}, data=fields)
    if r.status_code >= 400:  # e.g. 413 too large: record it as a result, keep going
        return f"UPLOAD_{r.status_code}", "", time.perf_counter() - started
    case_id = r.json()["case_id"]
    while True:
        result = client.get(f"/cases/{case_id}").json()
        if result["status"] in ("done", "failed"):
            break
        if time.perf_counter() - started > timeout:
            return "TIMEOUT", case_id, time.perf_counter() - started
        time.sleep(1)
    return result.get("verdict", "FAILED"), case_id, time.perf_counter() - started


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--library", type=Path, default=Path("samples/library"))
    p.add_argument("--held-out", nargs="*", default=[], help="file names kept out of the library")
    p.add_argument("--pitch", type=Path, nargs="*", default=[])
    p.add_argument("--max-per-group", type=int, default=6)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--timeout", type=float, default=240)
    p.add_argument("--out", type=Path, default=Path("docs/test-results.md"))
    args = p.parse_args()

    from farq.settings import get_settings

    key = get_settings().intake_api_key.get_secret_value()
    work = Path("samples/testset")
    work.mkdir(parents=True, exist_ok=True)
    items = build(args, work)
    print(f"{len(items)} test videos")

    rows = []
    with httpx.Client(base_url=args.base_url, headers={"X-API-Key": key}, timeout=120) as client:
        for group, name, path in items:
            verdict, case_id, seconds = run(client, path, args.timeout)
            ok = (verdict in SCAM) == (EXPECTED[group] in SCAM)
            rows.append((group, name, verdict, ok, seconds, case_id))
            print(f"{'ok ' if ok else 'MISS'} {group:<9} {verdict:<15} {seconds:5.1f} s  {name}")

    lines = [
        "# FARQ test-set results",
        "",
        f"Run {datetime.now(UTC):%Y-%m-%d %H:%M} UTC against {args.base_url}. "
        "All videos made from the team's consented clips with FFmpeg; "
        "'squeezed' = 480p, H.264 CRF 30, AAC 64k (an approximation of WhatsApp).",
        "",
        "| Group | Expected | Correct | Total |",
        "|---|---|---|---|",
    ]
    for group in EXPECTED:
        for squeezed in (False, True):
            sub = [r for r in rows if r[0] == group and r[1].endswith("(squeezed)") == squeezed]
            if sub:
                label = f"{group}{' (squeezed)' if squeezed else ''}"
                lines.append(
                    f"| {label} | {EXPECTED[group]} | {sum(r[3] for r in sub)} | {len(sub)} |"
                )
    times = sorted(r[4] for r in rows if r[2] != "TIMEOUT")
    if times:
        lines += ["", f"Upload to verdict: median {times[len(times) // 2]:.1f} s, "
                      f"slowest {times[-1]:.1f} s ({len(times)} videos)."]  # fmt: skip
    lines += ["", "| Group | Video | Verdict | Correct | Seconds |", "|---|---|---|---|---|"]
    lines += [f"| {g} | {n} | {v} | {'yes' if ok else 'no'} | {s:.1f} |"
              for g, n, v, ok, s, _ in rows]  # fmt: skip
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
