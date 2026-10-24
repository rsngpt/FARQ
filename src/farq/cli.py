"""Command-line tools. `farq check FILE` uploads a file to the local API and
prints the reply a user would get (also a no-chat fallback for the demo)."""

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

    args = parser.parse_args(argv)
    return _check(args)


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
            view = client.get(f"/cases/{case_id}").json()
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
