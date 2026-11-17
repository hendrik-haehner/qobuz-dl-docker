"""Qobuz-Anmeldung: erzeugt die qobuz-dl-Konfiguration ohne interaktive Eingabe.

qobuz-dl fragt beim ersten Start per input() nach E-Mail und Passwort. Im
Container geht das nicht, darum bauen wir dieselbe config.ini hier nach
(siehe qobuz_dl/cli.py: _reset_config), aus dem Webinterface oder beim Start
aus QOBUZ_EMAIL/QOBUZ_PASSWORD (python -m app.qobuz_config).
Gespeichert wird wie bei qobuz-dl nur der MD5-Hash des Passworts.
"""

import configparser
import hashlib
import logging
import os
import sys
import threading

from app.settings import Settings, get_settings

log = logging.getLogger("qobuz_config")

VALID_QUALITIES = (5, 6, 7, 27)


def build_config(
    email: str,
    password: str,
    app_id: str,
    secrets: list[str],
    *,
    shares_dir: str,
    quality: int,
    folder_format: str,
    track_format: str,
) -> configparser.ConfigParser:
    if quality not in VALID_QUALITIES:
        raise ValueError(f"Ungültige Qualität {quality}, erlaubt: {VALID_QUALITIES}")
    config = configparser.ConfigParser()
    d = config["DEFAULT"]
    d["email"] = email
    d["password"] = hashlib.md5(password.encode("utf-8")).hexdigest()
    d["default_folder"] = shares_dir
    d["default_quality"] = str(quality)
    d["default_limit"] = "20"
    for flag in (
        "no_m3u",
        "albums_only",
        "no_fallback",
        "og_cover",
        "embed_art",
        "no_cover",
        "no_database",
        "smart_discography",
    ):
        d[flag] = "false"
    d["app_id"] = app_id
    d["secrets"] = ",".join(secrets)
    d["folder_format"] = folder_format
    d["track_format"] = track_format
    return config


class LoginError(Exception):
    """Anmeldung bei Qobuz fehlgeschlagen; Meldung ist für die Oberfläche gedacht."""


_login_lock = threading.Lock()


def account(settings: Settings) -> dict:
    """Wer ist angemeldet? Gibt nie das Passwort (bzw. dessen Hash) heraus."""
    config = configparser.ConfigParser()
    try:
        config.read(settings.config_file)
        email = config["DEFAULT"].get("email") or None
    except (configparser.Error, OSError):
        email = None
    return {"configured": settings.config_file.is_file(), "email": email}


def _fetch_tokens() -> tuple[str, list[str]]:
    from qobuz_dl.bundle import Bundle

    log.info("Hole app_id und Secrets von play.qobuz.com ...")
    bundle = Bundle()
    secrets = [s for s in bundle.get_secrets().values() if s]
    return str(bundle.get_app_id()), secrets


def _verify(email: str, password_md5: str, app_id: str, secrets: list[str]) -> str:
    """Meldet sich wie qobuz-dl an. Gibt die Abo-Stufe zurück."""
    from qobuz_dl.qopy import Client

    client = Client(email, password_md5, app_id, secrets)
    return getattr(client, "label", "")


def login(settings: Settings, email: str, password: str) -> dict:
    """Zugangsdaten bei Qobuz prüfen und erst dann in config.ini schreiben."""
    import requests
    from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK
    from qobuz_dl.exceptions import (
        AuthenticationError,
        IneligibleError,
        InvalidAppIdError,
        InvalidAppSecretError,
    )

    email = email.strip()
    if not email or not password:
        raise LoginError("E-Mail/Benutzername und Passwort angeben.")

    with _login_lock:
        try:
            app_id, secrets = _fetch_tokens()
            config = build_config(
                email,
                password,
                app_id,
                secrets,
                shares_dir=str(settings.shares_dir),
                quality=settings.default_quality if settings.default_quality in VALID_QUALITIES else 6,
                folder_format=DEFAULT_FOLDER,
                track_format=DEFAULT_TRACK,
            )
            membership = _verify(email, config["DEFAULT"]["password"], app_id, secrets)
        except AuthenticationError as exc:
            raise LoginError("E-Mail/Benutzername oder Passwort ist falsch.") from exc
        except IneligibleError as exc:
            raise LoginError(
                "Dieses Qobuz-Konto darf nicht herunterladen (kostenloses Konto?)."
            ) from exc
        except (InvalidAppIdError, InvalidAppSecretError, NotImplementedError) as exc:
            raise LoginError(
                "Qobuz hat die App-Kennung abgelehnt. Eventuell braucht qobuz-dl ein Update."
            ) from exc
        except requests.RequestException as exc:
            raise LoginError(f"Qobuz ist nicht erreichbar: {exc.__class__.__name__}") from exc

        settings.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = settings.config_file.with_suffix(".tmp")
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            config.write(fh)
        os.replace(tmp, settings.config_file)
    log.info("Angemeldet als %s (%s)", email, membership or "Abo unbekannt")
    return {**account(settings), "membership": membership}


def logout(settings: Settings) -> None:
    with _login_lock:
        settings.config_file.unlink(missing_ok=True)


def ensure_config() -> bool:
    """Beim Containerstart: config.ini aus QOBUZ_EMAIL/QOBUZ_PASSWORD anlegen, falls sie fehlt."""
    settings = get_settings()
    if settings.config_file.is_file():
        log.info("Konfiguration vorhanden: %s", settings.config_file)
        return True

    email = os.environ.get("QOBUZ_EMAIL", "").strip()
    password = os.environ.get("QOBUZ_PASSWORD", "")
    if not email or not password:
        log.info("Noch kein Qobuz-Konto hinterlegt. Anmeldung im Webinterface möglich.")
        return False
    try:
        login(settings, email, password)
    except LoginError as exc:
        log.error("Anmeldung mit QOBUZ_EMAIL/QOBUZ_PASSWORD fehlgeschlagen: %s", exc)
        return False
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        ensure_config()
    except Exception as exc:  # Start des Webservers nicht blockieren
        log.error("Konfiguration konnte nicht erzeugt werden: %s", exc)
    sys.exit(0)
