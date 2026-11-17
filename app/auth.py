"""Zugangsschutz für das Webinterface: ein Passwort aus WEB_PASSWORD.

Nach dem Anmelden gibt es ein signiertes Session-Cookie (HttpOnly,
SameSite=Strict, bei HTTPS auch Secure). Der Signaturschlüssel hängt vom
Passwort ab: Wer WEB_PASSWORD ändert, meldet damit alle Sitzungen ab.
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path

COOKIE = "qdl_session"
SESSION_SECONDS = 30 * 24 * 3600
# Schutz gegen Durchprobieren: höchstens so viele Fehlversuche pro Zeitfenster (global)
MAX_FAILURES = 10
FAILURE_WINDOW = 300

_lock = threading.Lock()
_failures: deque[float] = deque()
_memory_secret = secrets.token_bytes(32)


def password() -> str:
    return os.environ.get("WEB_PASSWORD", "")


def enabled() -> bool:
    return bool(password())


def _secret(config_dir: Path) -> bytes:
    """Zufälliger Schlüssel im Config-Ordner, damit Sitzungen Neustarts überleben."""
    path = config_dir / "session.key"
    try:
        data = path.read_bytes()
        if len(data) >= 32:
            return data
    except OSError:
        pass
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        data = secrets.token_bytes(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return data
    except FileExistsError:
        return path.read_bytes()
    except OSError:
        # Config-Ordner nicht beschreibbar: Sitzungen gelten nur bis zum Neustart
        return _memory_secret


def _key(config_dir: Path) -> bytes:
    return hmac.new(_secret(config_dir), password().encode(), hashlib.sha256).digest()


def _sign(key: bytes, payload: str) -> str:
    return hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()


def create_token(config_dir: Path, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_SECONDS)
    payload = f"{expires}.{secrets.token_hex(8)}"
    return f"{payload}.{_sign(_key(config_dir), payload)}"


def valid_token(config_dir: Path, token: str | None, now: float | None = None) -> bool:
    if not token or not enabled():
        return False
    try:
        expires, nonce, sig = token.split(".")
        if int(expires) < (now or time.time()):
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sig, _sign(_key(config_dir), f"{expires}.{nonce}"))


class TooManyAttempts(Exception):
    pass


def check_password(candidate: str, now: float | None = None) -> bool:
    now = now or time.time()
    with _lock:
        while _failures and _failures[0] < now - FAILURE_WINDOW:
            _failures.popleft()
        if len(_failures) >= MAX_FAILURES:
            raise TooManyAttempts()
        ok = enabled() and hmac.compare_digest(candidate.encode(), password().encode())
        if not ok:
            _failures.append(now)
        return ok


def reset_failures() -> None:
    with _lock:
        _failures.clear()
