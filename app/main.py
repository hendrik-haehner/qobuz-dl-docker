"""Webinterface und REST-API für qobuz-dl."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.jobs import JobManager
from app.settings import get_settings

STATIC = Path(__file__).parent / "static"


class DownloadRequest(BaseModel):
    url: str
    quality: int | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = JobManager(get_settings())
    manager.start()
    app.state.jobs = manager
    yield
    await manager.stop()


app = FastAPI(title="qobuz-dl web", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    s = get_settings()
    return {
        "configured": s.config_file.is_file(),
        "download_dir": str(s.download_dir),
        "default_quality": s.default_quality,
    }


@app.get("/api/downloads")
def list_downloads():
    return [job.to_dict() for job in app.state.jobs.list()]


@app.get("/api/downloads/{job_id}")
def get_download(job_id: str):
    job = app.state.jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job nicht gefunden")
    return job.to_dict()


@app.post("/api/downloads", status_code=202)
def create_download(req: DownloadRequest):
    settings = get_settings()
    if not settings.config_file.is_file():
        # Sonst bleibt qobuz-dl in seiner interaktiven Ersteinrichtung hängen
        raise HTTPException(
            409, "qobuz-dl ist nicht konfiguriert: QOBUZ_EMAIL und QOBUZ_PASSWORD setzen."
        )
    quality = req.quality if req.quality is not None else settings.default_quality
    try:
        job = app.state.jobs.submit(req.url, quality)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return job.to_dict()
