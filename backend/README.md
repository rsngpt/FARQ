# FARQ

Forward a suspicious financial video, voice note or screenshot to the FARQ bot
and get a verdict (CONFIRMED SCAM / LIKELY SCAM / NOT VERIFIED), the reasons,
and what to do next.

Team Off-Grid, Amazon AI Cyber Security Hackathon finale, Track 3.

## Run it

Needs Docker Desktop (WSL2 backend) and [uv](https://docs.astral.sh/uv/).

```powershell
copy .env.example .env      # then replace every change-me value
docker compose up --build
```

- API health check: http://127.0.0.1:8000/healthz
- S3 media store (SeaweedFS): http://127.0.0.1:8333 (keys from `.env`)
- GPU worker (NVIDIA only): `docker compose --profile gpu up --build`

All ports are bound to 127.0.0.1, so nothing is reachable from other machines.

## Check a file (no chat app needed)

With the stack running:

```powershell
uv run farq check path\to\video.mp4
uv run farq check path\to\video.mp4 --money-sent yes
```

It uploads to the local API, waits for the verdict, and prints the reply a user
would get plus each stage's timing. Latency for the demo panel:
http://127.0.0.1:8000/metrics/latency

## Database changes

Tables live in `src/farq/storage/tables.py`. After changing them, generate a
migration from the laptop (use 127.0.0.1, not localhost):

```powershell
$env:POSTGRES_HOST = "127.0.0.1"; uv run alembic revision --autogenerate -m "what changed"
```

Read the generated file before committing. Migrations run automatically on
`docker compose up` (the `migrate` service).

## Develop

Tests make small synthetic videos, so FFmpeg must be on your PATH
(`winget install -e --id Gyan.FFmpeg`, then open a new terminal).

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
```

See `PLAN.md` for owners, timeline, bugs and decisions.
