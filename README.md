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

## Develop

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format .
```

See `PLAN.md` for owners, timeline, bugs and decisions.
