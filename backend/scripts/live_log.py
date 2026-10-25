"""Live server log for the demo screen: every case as it moves through the
pipeline, with what each check found and the verdict. Read-only: it only
watches the database.

    uv run python scripts/live_log.py            # new cases from now on
    uv run python scripts/live_log.py --replay 4 # show the last 4 cases first

Shows no user identifiers (no phone numbers or user hashes of the people who
sent the video); the scammer's numbers and UPI IDs found in a video are shown.
"""

import argparse
import os
import time
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from farq.settings import get_settings
from farq.storage.tables import ArtifactRow, CaseRow, EvidenceRow, StageRunRow

os.system("")  # turns on ANSI colours in the Windows console

STAGES = {
    "ingest": "Reading the video, taking picture fingerprints (PDQ)",
    "lookup": "Checking known scam files",
    "ocr": "Reading on-screen text (PaddleOCR)",
    "transcribe": "Listening to the speech (Whisper large-v3-turbo)",
    "entities": "Finding phone numbers, UPI IDs and links",
    "source_map": "Searching for the original and comparing faces (PDQ, BGE-M3, MediaPipe)",
    "analyse": "Voice-and-body sync check",
}
VERDICT_COLOURS = {"confirmed_scam": "91", "likely_scam": "93", "not_verified": "96"}


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m"


def stamp(at: datetime) -> str:
    return paint(at.astimezone().strftime("%H:%M:%S"), "90")


class Watcher:
    def __init__(self, session: Session):
        self.session = session
        self.seen: set[tuple] = set()

    def once(self, case_ids: list) -> None:
        for case in self.session.scalars(select(CaseRow).where(CaseRow.id.in_(case_ids))
                                         .order_by(CaseRow.created_at)):  # fmt: skip
            self.show_case(case)

    def show_case(self, case: CaseRow) -> None:
        short = str(case.id)[:8]
        if ("new", case.id) not in self.seen:
            self.seen.add(("new", case.id))
            ctx = case.context or {}
            kind = ctx.get("media_type") or "video"
            fwd = " · forwarded" if ctx.get("is_forwarded") else ""
            print()
            print(f"{stamp(case.created_at)}  {paint('NEW CASE', '1;97')} {short}  "
                  f"{kind} · {case.media_bytes / 1e6:.1f} MB{fwd}")  # fmt: skip
        runs = self.session.scalars(select(StageRunRow).where(StageRunRow.case_id == case.id)
                                    .order_by(StageRunRow.started_at))  # fmt: skip
        for run in runs:
            if run.stage not in STAGES or (run.stage, case.id) in self.seen:
                continue
            self.seen.add((run.stage, case.id))
            took = (run.ended_at - run.started_at).total_seconds()
            mark = paint("✗", "91") if run.status == "failed" else paint("✓", "92")
            print(f"{stamp(run.ended_at)}    {mark} {STAGES[run.stage]:<76} {took:5.1f} s")
            self.show_found(case, run.stage)
        if case.decision and ("verdict", case.id) not in self.seen:
            self.seen.add(("verdict", case.id))
            verdict = case.decision["verdict"]
            took = (max(r.ended_at for r in self.session.scalars(
                select(StageRunRow).where(StageRunRow.case_id == case.id))) - case.created_at
            ).total_seconds()  # fmt: skip
            label = paint(f" {verdict.upper()} ", f"1;{VERDICT_COLOURS.get(verdict, '97')};7")
            print(f"{' ' * 10}  VERDICT {label}  rule: {case.decision.get('rule_id', '-')}  "
                  f"· {took:.1f} s from upload")  # fmt: skip

    def artifact(self, case: CaseRow, kind: str) -> dict:
        query = select(ArtifactRow).where(ArtifactRow.case_id == case.id, ArtifactRow.kind == kind)
        art = self.session.scalars(query).first()
        return art.data if art else {}

    def show_found(self, case: CaseRow, stage: str) -> None:
        if stage == "entities":
            for e in self.artifact(case, "entities").get("entities", [])[:4]:
                print(f"{' ' * 14}{paint('found', '95')} {e['kind']}: {e['value']}")
        if stage == "transcribe":
            segments = self.artifact(case, "transcript").get("segments", [])
            text = " ".join(s["text"] for s in segments)
            if text:
                more = "…" if len(text) > 110 else ""
                print(f"{' ' * 14}{paint('heard', '95')} “{text[:110]}{more}”")
        for ev in self.session.scalars(select(EvidenceRow).where(
                EvidenceRow.case_id == case.id, EvidenceRow.stage == stage)):  # fmt: skip
            colour = "91" if ev.indicates == "scam" and ev.strength != "weak" else (
                "92" if ev.indicates == "not_scam" else "33")  # fmt: skip
            tag = paint(f"[{ev.strength} · {ev.type}]", colour)
            print(f"{' ' * 14}{tag} {ev.reason}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replay", type=int, default=0, help="show the last N cases first")
    args = parser.parse_args()

    url = get_settings().database_url
    if url.host not in ("localhost", "127.0.0.1"):
        url = url.set(host="127.0.0.1")  # the compose port is bound to localhost
    engine = create_engine(url)
    print(paint("FARQ live server log", "1;97"), paint("· watching for cases", "90"))
    started = datetime.now().astimezone()
    with Session(engine) as session:
        watcher = Watcher(session)
        if args.replay:
            ids = list(session.scalars(select(CaseRow.id).order_by(CaseRow.created_at.desc())
                                       .limit(args.replay)))  # fmt: skip
            watcher.once(ids)
        while True:
            session.expire_all()
            ids = list(session.scalars(select(CaseRow.id).where(CaseRow.created_at >= started)))
            open_ids = [i for i in ids if ("verdict", i) not in watcher.seen]
            watcher.once(open_ids)
            session.rollback()
            time.sleep(0.5)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
