"""Command-line tools.

`farq check FILE` uploads a file to the local API and prints the reply a user
would get (also a no-chat fallback for the demo).

`farq library add FILE ...` adds a genuine clip to the source-map library;
`farq library list` shows what's in it. These run Whisper, so stop the GPU
worker first (see README) to keep one copy of the model on the GPU.
"""

import argparse
import sys
import time
from pathlib import Path

import httpx

from farq.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="farq", description="FARQ command-line tools")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="check a file and print the reply")
    check.add_argument("file", type=Path)
    check.add_argument("--money-sent", choices=["yes", "no"])
    check.add_argument("--claimed-person", help="who the video claims to be")
    check.add_argument("--message-id", help="reuse to test dedupe (same ID, same case)")
    check.add_argument("--api", default="http://127.0.0.1:8000")
    check.add_argument("--timeout", type=float, default=120, help="seconds to wait")

    library = commands.add_parser("library", help="manage the library of genuine clips")
    library_cmds = library.add_subparsers(dest="library_command", required=True)
    add = library_cmds.add_parser("add", help="add a genuine clip")
    add.add_argument("files", type=Path, nargs="+")
    add.add_argument("--person", required=True, help="who the clip shows, e.g. 'enrolled-1'")
    add.add_argument("--source", required=True, help="e.g. 'team recording, 24 Oct' or a URL")
    add.add_argument("--consent", help="consent note, e.g. 'consent-video-AB.mp4'")
    add.add_argument("--title", help="defaults to the file name")
    library_cmds.add_parser("list", help="list library clips")

    args = parser.parse_args(argv)
    if args.command == "library":
        return _library(args)
    return _check(args)


def _library(args: argparse.Namespace) -> int:
    from farq.library import add_clip, load_clips
    from farq.storage.db import get_sessionmaker

    with get_sessionmaker()() as session:
        if args.library_command == "list":
            clips = load_clips(session)
            for c in clips:
                words = len((c.transcript or {}).get("text", "").split())
                frames = len(c.fingerprints["frames"])
                print(
                    f"{c.id}  {c.person:<12} {c.duration_s:6.1f} s  "
                    f"{frames:4} frames  {words:4} words  {c.title}"
                )
            print(f"{len(clips)} clip(s)")
            return 0

        from farq.asr.engine import get_asr_engine
        from farq.storage.media import S3MediaStore

        settings = get_settings()
        media = S3MediaStore.from_settings(settings)
        media.ensure_bucket()
        asr = get_asr_engine(
            settings.whisper_model_dir, settings.whisper_gpu_compute_type,
            settings.whisper_beam_size,
        )  # fmt: skip
        from farq.embed import get_embedder

        embedder = get_embedder(settings.bge_m3_dir, settings.bge_m3_revision,
                                settings.embed_threads)  # fmt: skip
        for path in args.files:
            started = time.perf_counter()
            clip_id, existed = add_clip(
                session, media, asr, path,
                person=args.person, title=args.title or path.stem,
                source=args.source, consent_note=args.consent, embedder=embedder,
            )  # fmt: skip
            note = (
                "already in library"
                if existed
                else f"added in {time.perf_counter() - started:.1f} s"
            )
            print(f"{path.name}: {clip_id} ({note})")
    return 0


def _check(args: argparse.Namespace) -> int:
    key = get_settings().intake_api_key.get_secret_value()
    if not key:
        print("INTAKE_API_KEY is not set (see .env.example)", file=sys.stderr)
        return 2
    if not args.file.is_file():
        print(f"No such file: {args.file}", file=sys.stderr)
        return 2

    form = {}
    if args.money_sent:
        form["money_sent"] = "true" if args.money_sent == "yes" else "false"
    if args.claimed_person:
        form["claimed_person"] = args.claimed_person
    if args.message_id:
        form["message_id"] = args.message_id

    with httpx.Client(base_url=args.api, headers={"X-API-Key": key}, timeout=60) as client:
        with args.file.open("rb") as f:
            response = client.post("/cases", files={"file": (args.file.name, f)}, data=form)
        if response.status_code != 202:
            print(f"Upload failed ({response.status_code}): {response.text}", file=sys.stderr)
            return 1
        created = response.json()
        case_id = created["case_id"]
        print(f"Case {case_id}" + (" (duplicate message)" if created["duplicate"] else ""))

        deadline = time.monotonic() + args.timeout
        while True:
            view = client.get(f"/cases/{case_id}/debug").json()
            if view["status"] in ("decided", "failed"):
                break
            if time.monotonic() > deadline:
                print(f"Still {view['status']} after {args.timeout:.0f} s", file=sys.stderr)
                return 1
            time.sleep(0.5)

    print()
    print(view["reply_text"] or f"Case {view['status']}, no reply")
    print()
    for stage in view["stages"]:
        note = f"  {stage['error']}" if stage["error"] else ""
        print(f"  {stage['stage']:<8} {stage['status']:<6} {stage['duration_ms']:>6} ms{note}")
    return 0 if view["status"] == "decided" else 1


if __name__ == "__main__":
    sys.exit(main())
