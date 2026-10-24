# FARQ plan

FARQ checks a forwarded video against its **sources** instead of only guessing
from pixels. Indian investment deepfakes are collages: real faces, voices taken
from other real videos, AI only on the lips. FARQ answers four questions, then an
investigator agent writes a sourced report.

1. **Source map:** where did every second come from (visual: vpdq vs official
   footage; speech: Whisper + BGE-M3 / exact n-grams vs real speeches)?
2. **Find the original + diff:** align in time, mouth-vs-rest-of-face change
   (MediaPipe), transcript diff.
3. **Audio-visual binding** (main detector, no original needed): pitch/loudness
   emphasis vs head pose + eyebrows, mouth ignored; windowed cross-correlation
   at +-300 ms. v1 heuristic calibrated per person; v2 small temporal-conv head
   on frozen WavLM Base+ + landmarks. Knockout test with the original audio.
4. **Supporting signals:** audio deepfake head (frozen WavLM / XLS-R), known-fake
   hash (sha256 + vpdq), scam-script match (BGE-M3), official lists (RBI Alert
   List, NSE caution notices, SEBI), numbers / UPI IDs / links (OCR first, then speech).

## Owners
| Area | Owner |
|---|---|
| Lead, design, integration | PENDING |
| Intake, channels, reviewer | PENDING |
| Source map + find-original | PENDING |
| Audio-visual binding + audio head | PENDING |
| Rules, investigator agent, reports | PENDING |
| Test set, metrics, demo | PENDING |

## Milestones
| # | What | Status |
|---|---|---|
| M1 | Intake + CaseFile + round trip (Telegram deferred; local upload first) | in progress |
| M2 | Ingest + OCR + Whisper + entities + known-fake hash | |
| M3 | Source map + find-original diff | |
| M4 | Audio-visual binding v1 + audio deepfake head | |
| M5 | Rules engine + investigator report + reviewer + police report | |
| M6 | Test set run (metrics) + demo polish | |

Code freeze: PENDING. Rehearsal: PENDING.

## Build steps
- [x] Repo structure and plan agreed
- [x] Scaffold: uv, ruff, pytest, Dockerfile, docker-compose, .env.example
- [x] M1 core: CaseFile + Evidence, Postgres tables + Alembic, upload intake
      (`POST /cases`, `farq check`), pipeline runner (stub stages + real
      known-fake sha256 lookup), YAML rules engine, audit log, /metrics/latency
- [ ] Telegram adapter (deferred for now)
- [x] M2.1 Each stage runs on its own queue (io / cpu / gpu); artifacts table
- [x] M2.2 Ingest: guarded ffprobe, keyframes (1/s, max 120), 16 kHz mono audio
- [x] M2 follow-up: plain "couldn't open this file" reply
- [x] M2.3 OCR: PaddleOCR, up to 12 frames, Hindi + English, merged lines with times
- [x] M2.4 Whisper large-v3-turbo (weights converted by us from OpenAI's), word timings
      (verified on laptop GPU and in the GPU container; live stack not yet rebuilt)
- [x] M2.5 Entities (numbers, UPI IDs, links, group links) + weak warning signs
      (guaranteed returns, group invite, urgency, UPI ID to pay into)
- [x] M2.6 Timing run on a 1-minute clip vs the 60 s target
- [ ] M2 leftover: vpdq near-duplicate known-fake hash (moved to M3 with the source map)
- [ ] Speed-up option: run OCR and Whisper side by side (they don't depend on each other)

M2.6 timing run (24 Oct, live stack on the laptop, 60.5 s synthetic video:
two overlay frames + the team's pitch and control recordings). Server time from
upload to verdict (/metrics/latency): 45.9 s for the first case after start,
38.7 s after. Per stage, first case: ingest 4.2 s, OCR 23.9 s, Whisper 14.4 s,
everything else < 0.1 s. Verify and analyse are still stubs (M3/M4), so this
is not the final number.

Measured so far (container, synthetic 47 s video with overlays and a team
recording): ingest 2.4 s, OCR 23 s for 12 frames. Whisper in the GPU
container: 9.9 s for the 47 s team pitch (model load 68.6 s from the Windows
bind mount, once per worker start). Spoken phone number lost one digit
(987654320); spoken UPI ID comes out in Devanagari, so OCR stays the main
source for exact IDs.

## Rules every stage follows
- Evidence rows carry: id, source_type (model / match / list / rule), strength
  (decisive / strong / weak), reason, model_name + model_version, timestamp.
- ML signals are shown as levels (low / medium / high), calibrated as a
  percentile against the person's genuine clips. Never raw scores.
- Abstain: weak or conflicting evidence gives NOT VERIFIED with warning signs and
  the official helpline. Never guess. Never call a video "genuine".
- The verdict comes from the YAML rules engine, never the LLM. The agent only
  writes the narrative, and every sentence cites an evidence ID.
- CONFIRMED only after a reviewer confirms; confirmed cases are cached.
- Audit log: every verdict and reviewer action stores who, when, evidence IDs,
  model versions.
- Stages are idempotent; intake dedupes on message ID.
- Stage start/end times recorded in the CaseFile; /metrics/latency for the demo
  panel. Targets: known fake < 10 s, new video < 60 s.
- Only the API is public; everything else binds to localhost.

## Outputs
- Chat reply: verdict, 2-4 plain reasons, next steps; source map + "what changed"
  as text and a timeline image when available.
- Police-portal report: pre-filled complaint text + evidence PDF (WeasyPrint)
  with SHA-256 hashes and timestamps, for the USER to file on cybercrime.gov.in.
  Money lost: "call 1930 now" first. Never auto-submitted.
- Reviewer: LIKELY cases go to a reviewer (Telegram, Confirm / Reject).
  Queue order: money already sent > frequently forwarded > other.
- Campaigns: cases sharing a known-fake hash, source clip or scam-script match
  are grouped, with first-seen time, count and timeline.

## Out of scope (do not build)
Circle, name checks (CNAP / UPI / SEBI @valid), institution "never says" records,
outbreak alerts, own number-reputation database, Android app, voice-note replies,
warning cards, physics / room-acoustics checks, watermarking.
Live-call help: only if time remains, as a simple text flow.

## Data
Public official videos + speech transcripts, public debunked scam videos,
team-recorded consented clips (enrolled team members). Test fakes made on-site
from team clips only. No real PII; phone numbers stored only as keyed hashes.

## Demo
An enrolled team member; a fresh stitched fake made from one of her clips. A
generic detector says "likely real" (detector: PENDING, must be a real run).
FARQ: "Altered. Face and voice are both hers but weren't recorded together."
Source map, original, changed words, coupling chart, then the knockout: original
audio back in, coupling snaps into step.

## Bugs
| # | Bug | Owner | Fixed |
|---|---|---|---|
| 1 | PaddlePaddle 3.3.1 crashes with oneDNN on OCR models (Windows and Linux) | - | worked around: oneDNN off |
| 2 | OCR on Windows laptop is slow (~2 min for the real-model test incl. download); container is fine | - | not needed for production |
| 3 | faster-whisper 1.2.1 breaks with current PyAV (`metadata_errors`) | - | worked around: pass samples, not a path |
| 4 | Whisper model load takes 40-68 s from the Windows bind mount | - | fixed: preloaded at worker start (OCR too) |
| 5 | Docker images + build cache filled C: (1.1 GB free); GPU image reported 13 GB | - | caches cleared; images slimmed (app 3.3 GB, GPU 7.1 GB, as Docker reports); Docker disk file still 35 GB until compacted |

## Decisions
- Product and code name: FARQ. Repo folder: RAKSHAM.
- Python 3.12 managed by uv; all services run in Docker (WSL2 backend on Windows).
- Celery + Redis; queues io, cpu, gpu. GPU worker runs one job at a time (6 GB VRAM)
  and sits behind a compose profile so teammates without NVIDIA GPUs can run the stack.
- Postgres 16 + pgvector.
- Media store: SeaweedFS 4.46 (S3-compatible) instead of MinIO, whose images were
  removed from Docker Hub. Code uses only the S3 API, so it can be swapped.
- Whisper large-v3-turbo via faster-whisper int8; frozen WavLM Base+ / CLIP as
  feature extractors; never two large models loaded at once.
- LLM: Claude on Amazon Bedrock (India profile), tool use, narrative only.
- Channels: WhatsApp (pywa) + Telegram (python-telegram-bot). Telegram deferred;
  a local upload endpoint is the first intake.
- Local tools connect to 127.0.0.1, not "localhost" (on Windows, localhost tries IPv6 first and hangs).
- Upload endpoint and case view need an X-API-Key; /healthz and /metrics/latency are open (no personal data).
- Telegram uses long polling locally; WhatsApp webhooks will need a public URL
  for the API only (Caddy or Cloudflare Tunnel: PENDING).
