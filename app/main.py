"""Webinterface und REST-API für qobuz-dl."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app import preferences, storage
from app.jobs import JobManager
from app.preferences import FOLDER_KEYS, TRACK_KEYS, Preferences
from app.settings import get_settings

STATIC = Path(__file__).parent / "static"


class DownloadRequest(BaseModel):
    """Nicht angegebene Felder kommen aus den gespeicherten Einstellungen."""

    url: str
    format: str | None = None
    quality: int | None = None
    target_dir: str | None = None
    folder_format: str | None = None
    track_format: str | None = None


class NewFolder(BaseModel):
    parent: str = ""
    name: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = JobManager(get_settings())
    manager.start()
    app.state.jobs = manager
    yield
    await manager.stop()


app = FastAPI(title="qobuz-dl web", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


def _bad_request(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        msg = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
    else:
        msg = str(exc)
    return HTTPException(422, msg)


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
        "placeholders": {
            "folder": sorted(FOLDER_KEYS),
            "track": sorted(TRACK_KEYS),
        },
    }


@app.get("/api/settings")
def get_preferences():
    return preferences.load(get_settings()).model_dump()


@app.put("/api/settings")
def put_preferences(prefs: dict):
    s = get_settings()
    try:
        new = Preferences.model_validate(prefs)
        storage.resolve(s.download_dir, new.target_dir)
    except (ValidationError, ValueError) as exc:
        raise _bad_request(exc) from exc
    try:
        preferences.save(s, new)
    except OSError as exc:
        raise HTTPException(
            500, f"Einstellungen konnten nicht gespeichert werden ({exc.strerror}). "
            "Hat der Container Schreibrechte auf den Config-Ordner (PUID/PGID)?"
        ) from exc
    return new.model_dump()


@app.get("/api/folders")
def get_folders(path: str = ""):
    try:
        return storage.list_dirs(get_settings().download_dir, path)
    except storage.StorageError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/folders", status_code=201)
def create_folder(req: NewFolder):
    try:
        path = storage.make_dir(get_settings().download_dir, req.parent, req.name)
    except storage.StorageError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"path": path}


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
    defaults = preferences.load(settings).model_dump()
    overrides = req.model_dump(exclude={"url"}, exclude_none=True)
    try:
        options = Preferences.model_validate(defaults | overrides)
        job = app.state.jobs.submit(req.url, options)
    except (ValidationError, ValueError) as exc:
        raise _bad_request(exc) from exc
    return job.to_dict()
