# FARQ demo runbook

Everything runs on the team laptop (RTX 4050). Only the API is public, through
a Cloudflare quick tunnel. Commands are PowerShell, from the repo folder.

## Before the event (once)

1. Library of the enrolled team member (see `docs/test-data/FARQ-recording-guide.pdf`):
   ```powershell
   docker compose stop worker-gpu
   docker compose run --rm --no-deps -v "${PWD}\samples:/app/samples:ro" worker-gpu `
     farq library add /app/samples/library/lib-01-intro.mp4 /app/samples/library/lib-02-upi.mp4 `
     --person enrolled-1 --source "team recording, consented" --consent "consent-video-XX.mp4"
   docker compose start worker-gpu
   ```
   Keep 2–4 clips out of the library for the test set.
2. Make the demo fakes (picture of one clip, voice of another or of the pitch) and
   run the test set: `uv run python scripts/run_testset.py --held-out <names> --pitch <pitch file>`.
   Results go to `docs/test-results.md`. Only these measured numbers go on slides.
3. Free disk space: Docker's disk file grows with every rebuild. Before the event,
   quit Docker Desktop and run the shrink steps (`wsl --shutdown`, then `diskpart`,
   `compact vdisk`) so C: has room.

## Start order (on the day)

| # | Step | Command | Check |
|---|---|---|---|
| 1 | Docker Desktop | Start menu → Docker Desktop | whale icon says "running" |
| 2 | Stack | `docker compose up -d --wait` | all services healthy: `docker compose ps` |
| 3 | Models loaded | `docker compose logs worker-gpu worker-cpu \| Select-String preloaded` | 4 lines: whisper, bge, ocr ×2 (about 1 min) |
| 4 | Tunnel | `cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8000` (leave open) | prints `https://….trycloudflare.com` |
| 5 | Tell Roshan | send the new link (it changes each time) | his `FARQ_API_BASE_URL` |
| 6 | Smoke test | `uv run python scripts/bot_smoke.py samples\<fake>.mp4 --base-url <link>` | `"verdict": "LIKELY_SCAM"` within ~60 s |

## Demo script (about 3 minutes)

1. **The problem (30 s).** A forwarded video of a familiar face promising guaranteed returns.
   Generic detectors look for synthetic pixels; collages use real faces and real voices.
2. **Forward it (60 s).** On a phone, forward the demo fake to the FARQ WhatsApp number.
   Answer the three buttons (who it claims to be, what it asks, money sent: yes).
   The bot shows "call 1930 now" first, then the verdict when ready.
3. **The verdict (60 s).** "This video has been altered. The face and the voice were not
   recorded together." Show the reasons, the scammer's number and UPI ID found, and
   the source map: picture from recording A, voice from recording B.
4. **The report (30 s).** Open the police-report PDF: findings with evidence IDs, file
   fingerprint, pre-filled complaint for cybercrime.gov.in. The user files it; FARQ never does.

Never say "genuine", "safe" or quote raw scores. NOT VERIFIED means "we couldn't verify it".

## If this breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot gets no reply | tunnel closed or link changed | restart the tunnel, send Roshan the new link |
| `401` from the API | API key mismatch | Roshan's `FARQ_API_KEY` must equal our `INTAKE_API_KEY` |
| Stuck at "processing" | a worker is down | `docker compose ps`; `docker compose restart worker-gpu worker-cpu` |
| First case very slow | models not preloaded yet | wait for the 4 `preloaded` lines |
| NOT_VERIFIED for a fake | picture or voice source not in the library | check `farq library list`; add the clip |
| Docker not answering | disk full or Docker stuck | free space; quit and restart Docker Desktop |

## Fallback (no WhatsApp, no internet)

Run the same check on the laptop and show the result on screen:
```powershell
uv run python scripts/bot_smoke.py samples\<fake>.mp4 --money-sent
```
It prints exactly what the bot would show. The PDF is at
`http://127.0.0.1:8000/cases/<case_id>/report.pdf` (needs the API key header; use the
debug view or `curl -H "X-API-Key: ..."` to save it).
