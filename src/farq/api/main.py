from fastapi import FastAPI

from farq.api import cases, metrics, reports

app = FastAPI(title="FARQ")
app.include_router(reports.router)  # signed links; no API key needed
app.include_router(cases.router)
app.include_router(metrics.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check: the API process is up."""
    return {"status": "ok"}
