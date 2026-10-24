from fastapi import FastAPI

app = FastAPI(title="FARQ")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check: the API process is up."""
    return {"status": "ok"}
