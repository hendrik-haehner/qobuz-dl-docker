"""Qobuz-Anmeldung: erzeugt die qobuz-dl-Konfiguration ohne interaktive Eingabe.

Qobuz nimmt seit April 2026 keine Anmeldung mit E-Mail/Passwort mehr an. Die
App meldet sich darum mit dem `user_auth_token` aus einer Browser-Sitzung an
(siehe app/token_auth.py). config.ini hat dasselbe Format wie bei qobuz-dl,
nur steht im Feld `password` der Token und zusätzlich `auth_method = token`.
Beim Start kann der Token auch aus QOBUZ_TOKEN kommen (python -m app.qobuz_config).
"""

import configparser
import logging
import os
import sys
import threading

from app.settings import Settings, get_settings

log = logging.getLogger("qobuz_config")

VALID_QUALITIES = (5, 6, 7, 27)


def build_config(
    email: str,
    token: str,
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
    d["password"] = token  # Token, kein Passwort-Hash (siehe app/token_auth.py)
    d["auth_method"] = "token"
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
    """Wer ist angemeldet? Gibt nie Token oder Passwort-Hash heraus."""
    config = configparser.ConfigParser()
    try:
        config.read(settings.config_file)
        email = config["DEFAULT"].get("email") or None
        method = config["DEFAULT"].get("auth_method", "password")
    except (configparser.Error, OSError):
        email, method = None, "password"
    configured = settings.config_file.is_file()
    return {
        "configured": configured,
        "email": email,
        # "password": alte Anmeldung (z. B. kopierte config.ini), lehnt Qobuz inzwischen ab
        "auth_method": method if configured else None,
    }


def _fetch_tokens() -> tuple[str, list[str]]:
    from qobuz_dl.bundle import Bundle

    log.info("Hole app_id und Secrets von play.qobuz.com ...")
    bundle = Bundle()
    secrets = [s for s in bundle.get_secrets().values() if s]
    return str(bundle.get_app_id()), secrets


def _verify(token: str, app_id: str, secrets: list[str]) -> dict:
    """Meldet sich wie ein Download mit dem Token an; gibt Kontodaten und frischen Token."""
    from app import token_auth

    return token_auth.login(token, app_id, secrets)


def login(settings: Settings, token: str) -> dict:
    """Token bei Qobuz prüfen und erst dann in config.ini schreiben."""
    import requests
    from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK
    from qobuz_dl.exceptions import (
        AuthenticationError,
        InvalidAppIdError,
        InvalidAppSecretError,
    )

    from app.token_auth import TokenError

    token = token.strip()
    if not token:
        raise LoginError("Bitte den Token aus dem Browser einfügen.")

    with _login_lock:
        try:
            app_id, secrets = _fetch_tokens()
            info = _verify(token, app_id, secrets)
        except (TokenError, AuthenticationError) as exc:
            raise LoginError(
                "Qobuz hat den Token abgelehnt: ungültig oder abgelaufen. "
                "Hol dir einen neuen aus dem Browser (Anleitung unter dem Feld)."
            ) from exc
        except (InvalidAppIdError, InvalidAppSecretError, NotImplementedError) as exc:
            raise LoginError(
                "Qobuz hat die App-Kennung abgelehnt. Eventuell braucht qobuz-dl ein Update."
            ) from exc
        except requests.RequestException as exc:
            raise LoginError(f"Qobuz ist nicht erreichbar: {exc.__class__.__name__}") from exc

        if not info["can_download"]:
            raise LoginError(
                "Angemeldet, aber Qobuz meldet für dieses Konto kein Download-Abo "
                f"({info['label'] or 'unbekannt'})."
            )
        config = build_config(
            info["email"],
            info["token"],  # frischer Token aus der Anmeldung
            app_id,
            secrets,
            shares_dir=str(settings.shares_dir),
            quality=settings.default_quality if settings.default_quality in VALID_QUALITIES else 6,
            folder_format=DEFAULT_FOLDER,
            track_format=DEFAULT_TRACK,
        )
        settings.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = settings.config_file.with_suffix(".tmp")
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
            config.write(fh)
        os.replace(tmp, settings.config_file)
    log.info("Angemeldet als %s (%s)", info["email"] or "?", info["label"] or "Abo unbekannt")
    return {**account(settings), "membership": info["label"]}


def logout(settings: Settings) -> None:
    with _login_lock:
        settings.config_file.unlink(missing_ok=True)


def ensure_config() -> bool:
    """Beim Containerstart: config.ini aus QOBUZ_TOKEN anlegen, falls sie fehlt."""
    settings = get_settings()
    if settings.config_file.is_file():
        log.info("Konfiguration vorhanden: %s", settings.config_file)
        return True

    token = os.environ.get("QOBUZ_TOKEN", "").strip()
    if not token:
        log.info("Noch kein Qobuz-Konto hinterlegt. Anmeldung im Webinterface möglich.")
        return False
    try:
        login(settings, token)
    except LoginError as exc:
        log.error("Anmeldung mit QOBUZ_TOKEN fehlgeschlagen: %s", exc)
        return False
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        ensure_config()
    except Exception as exc:  # Start des Webservers nicht blockieren
        log.error("Konfiguration konnte nicht erzeugt werden: %s", exc)
    sys.exit(0)
