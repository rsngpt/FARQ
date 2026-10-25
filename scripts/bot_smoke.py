"""Act like the WhatsApp bot against a FARQ backend: upload a file with the bot's
fields, send the guided answers while it runs, poll, and print the result.

    uv run python scripts/bot_smoke.py FILE [--base-url URL] [--money-sent]

The API key is read from FARQ_API_KEY, or from INTAKE_API_KEY in .env.
Prints only the result JSON and timings; never prints the key.
"""

import argparse
import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

KINDS = {".mp4": "video", ".mov": "video", ".webm": "video", ".3gp": "video",
         ".ogg": "audio", ".opus": "audio", ".mp3": "audio", ".m4a": "audio", ".wav": "audio",
         ".jpg": "image", ".jpeg": "image", ".png": "image", ".webp": "image"}  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", type=Path)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--money-sent", action="store_true")
    parser.add_argument("--claims-to-be", default="official", help="e.g. family_friend")
    parser.add_argument("--asks-for", default="invest", help="guided answer, e.g. send_money")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    key = os.environ.get("FARQ_API_KEY")
    if not key:
        from farq.settings import get_settings

        key = get_settings().intake_api_key.get_secret_value()
    if not key:
        sys.exit("Set FARQ_API_KEY (or INTAKE_API_KEY in .env)")

    fields = {
        "media_type": KINDS.get(args.file.suffix.lower(), "video"),
        "idempotency_key": f"c_smoke_{uuid.uuid4().hex[:10]}",
        "user_ref": "smoke-test-user",
        "is_forwarded": "true",
        "frequently_forwarded": "false",
        "language": "hi",
        "received_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, headers={"X-API-Key": key}, timeout=60) as c:
        with args.file.open("rb") as f:
            r = c.post("/cases", files={"file": (args.file.name, f)}, data=fields)
        print(f"POST /cases -> {r.status_code} {r.json()}")
        r.raise_for_status()
        case_id = r.json()["case_id"]

        answers = {"claims_to_be": args.claims_to_be, "asks_for": args.asks_for,
                   "money_sent": args.money_sent}  # fmt: skip
        r = c.patch(f"/cases/{case_id}/answers", json=answers)
        print(f"PATCH answers -> {r.status_code} {r.json()}")

        while True:
            result = c.get(f"/cases/{case_id}").json()
            if result["status"] in ("done", "failed"):
                break
            if time.perf_counter() - started > args.timeout:
                sys.exit(f"Still {result['status']} after {args.timeout:.0f} s")
            time.sleep(1)
    print(f"\nupload to result: {time.perf_counter() - started:.1f} s\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
