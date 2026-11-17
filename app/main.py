"""Webinterface und REST-API für qobuz-dl."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from app import auth, preferences, qobuz_config, storage
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


class Credentials(BaseModel):
    email: str
    password: str


class WebLogin(BaseModel):
    password: str


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

# Ohne Anmeldung erreichbar (Healthcheck, Login-Seite und deren Dateien)
PUBLIC = {"/login", "/api/login", "/api/health", "/static/style.css", "/static/login.js"}


def _logged_in(request: Request) -> bool:
    return auth.valid_token(get_settings().config_dir, request.cookies.get(auth.COOKIE))


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if not auth.enabled() or path in PUBLIC or _logged_in(request):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "Nicht angemeldet."}, status_code=401)
    return RedirectResponse("/login", status_code=303)


def _bad_request(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        msg = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
    else:
        msg = str(exc)
    return HTTPException(422, msg)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if not auth.enabled() or _logged_in(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(STATIC / "login.html")


@app.post("/api/login", status_code=204)
async def web_login(req: WebLogin, request: Request, response: Response):
    if not auth.enabled():
        return
    try:
        ok = auth.check_password(req.password)
    except auth.TooManyAttempts as exc:
        raise HTTPException(429, "Zu viele Fehlversuche. Bitte in ein paar Minuten erneut.") from exc
    if not ok:
        await asyncio.sleep(1)  # bremst Durchprobieren
        raise HTTPException(401, "Falsches Passwort.")
    response.set_cookie(
        auth.COOKIE,
        auth.create_token(get_settings().config_dir),
        max_age=auth.SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


@app.post("/api/logout", status_code=204)
def web_logout(response: Response):
    response.delete_cookie(auth.COOKIE, httponly=True, samesite="strict")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status():
    s = get_settings()
    return {
        **qobuz_config.account(s),
        "auth_enabled": auth.enabled(),
        "shares_dir": str(s.shares_dir),
        "placeholders": {
            "folder": sorted(FOLDER_KEYS),
            "track": sorted(TRACK_KEYS),
        },
    }


@app.get("/api/account")
def get_account():
    return qobuz_config.account(get_settings())


@app.put("/api/account")
def put_account(creds: Credentials):
    """Zugangsdaten bei Qobuz prüfen und speichern (Dauer: einige Sekunden)."""
    try:
        return qobuz_config.login(get_settings(), creds.email, creds.password)
    except qobuz_config.LoginError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(
            500, f"Zugangsdaten konnten nicht gespeichert werden ({exc.strerror}). "
            "Hat der Container Schreibrechte auf den Config-Ordner (PUID/PGID)?"
        ) from exc


@app.delete("/api/account", status_code=204)
def delete_account():
    qobuz_config.logout(get_settings())


@app.get("/api/settings")
def get_preferences():
    return preferences.load(get_settings()).model_dump()


@app.put("/api/settings")
def put_preferences(prefs: dict):
    s = get_settings()
    try:
        new = Preferences.model_validate(prefs)
        if new.target_dir:  # leer = „noch nicht gewählt“
            storage.check_target(s.shares_dir, new.target_dir)
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
        return storage.list_dirs(get_settings().shares_dir, path)
    except storage.StorageError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/folders", status_code=201)
def create_folder(req: NewFolder):
    try:
        path = storage.make_dir(get_settings().shares_dir, req.parent, req.name)
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
        raise HTTPException(409, "Bitte zuerst oben mit deinem Qobuz-Konto anmelden.")
    defaults = preferences.load(settings).model_dump()
    overrides = req.model_dump(exclude={"url"}, exclude_none=True)
    try:
        options = Preferences.model_validate(defaults | overrides)
        if not options.target_dir:
            options.target_dir = storage.default_target(settings.shares_dir)
        job = app.state.jobs.submit(req.url, options)
    except (ValidationError, ValueError) as exc:
        raise _bad_request(exc) from exc
    return job.to_dict()
