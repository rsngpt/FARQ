# FARQ plan

## Owners
| Area | Owner |
|---|---|
| Lead, design, integration | PENDING |
| Channels (Telegram, WhatsApp) | PENDING |
| Pipeline and decision engine | PENDING |
| Detectors (audio, video) | PENDING |
| Demo and slides | PENDING |

## Timeline
| When | What |
|---|---|
| Day 1 | Scaffold, Telegram end to end, CaseFile + Evidence, decision engine, detector interface, ingest |
| Day 1 evening | PENDING |
| Day 2 | PENDING |
| Code freeze | PENDING |
| Rehearsal | PENDING |

## Build steps
- [x] 1. Repo structure and plan agreed
- [x] 2. Scaffold: uv, ruff, pytest, Dockerfile, docker-compose, .env.example
- [ ] 3. Telegram adapter: receive a video, store it, reply "Got it, checking"
- [ ] 4. CaseFile + Evidence, pipeline with stub stages, decision engine, verdict reply
- [ ] 5. Detector plugin interface + one dummy detector
- [ ] 6. Ingest stage: ffprobe, sha256, keyframes, 16 kHz mono audio

## Bugs
| # | Bug | Owner | Fixed |
|---|---|---|---|

## Decisions
- Product and code name: FARQ. Repo folder: RAKSHAM.
- Python 3.12 managed by uv; all services run in Docker (WSL2 backend on Windows).
- Celery + Redis now, not Temporal (less setup; stages stay plain functions so a swap is cheap).
- Queues: io, cpu, gpu. The GPU worker runs one job at a time (6 GB VRAM).
- GPU worker is behind a compose profile so teammates without NVIDIA GPUs can still run the stack.
- All ports bound to 127.0.0.1.
- Media store: SeaweedFS 4.46 (S3-compatible) instead of MinIO, whose images were removed from Docker Hub. Code uses only the S3 API, so it can be swapped.
- Telegram uses long polling locally (nothing exposed to the internet); webhook route built for deployment.
- Users see reasons and a level (low / medium / high), never raw scores.
