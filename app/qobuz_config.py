"""Erzeugt die qobuz-dl-Konfiguration ohne interaktive Eingabe.

qobuz-dl fragt beim ersten Start per input() nach E-Mail und Passwort. Im
Container geht das nicht, darum bauen wir dieselbe config.ini hier aus
Umgebungsvariablen nach (siehe qobuz_dl/cli.py: _reset_config).

Aufruf: python -m app.qobuz_config
"""

import configparser
import hashlib
import logging
import os
import sys

from app.settings import get_settings

log = logging.getLogger("qobuz_config")

VALID_QUALITIES = (5, 6, 7, 27)


def build_config(
    email: str,
    password: str,
    app_id: str,
    secrets: list[str],
    *,
    download_dir: str,
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
    d["default_folder"] = download_dir
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


def ensure_config() -> bool:
    """Legt config.ini an, falls sie fehlt. Gibt True zurück, wenn eine Config existiert."""
    settings = get_settings()
    if settings.config_file.is_file():
        log.info("Konfiguration vorhanden: %s", settings.config_file)
        return True

    email = os.environ.get("QOBUZ_EMAIL", "").strip()
    password = os.environ.get("QOBUZ_PASSWORD", "")
    if not email or not password:
        log.warning(
            "Keine Konfiguration unter %s und QOBUZ_EMAIL/QOBUZ_PASSWORD nicht gesetzt. "
            "Das Webinterface startet trotzdem, Downloads schlagen aber fehl.",
            settings.config_file,
        )
        return False

    # Erst hier importieren: holt app_id und Secrets von play.qobuz.com
    from qobuz_dl.bundle import Bundle
    from qobuz_dl.downloader import DEFAULT_FOLDER, DEFAULT_TRACK

    log.info("Hole app_id und Secrets von play.qobuz.com ...")
    bundle = Bundle()
    config = build_config(
        email,
        password,
        str(bundle.get_app_id()),
        list(bundle.get_secrets().values()),
        download_dir=str(settings.download_dir),
        quality=settings.default_quality,
        folder_format=DEFAULT_FOLDER,
        track_format=DEFAULT_TRACK,
    )
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    with open(settings.config_file, "w") as fh:
        config.write(fh)
    os.chmod(settings.config_file, 0o600)
    log.info("Konfiguration geschrieben: %s", settings.config_file)
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        ensure_config()
    except Exception as exc:  # Start des Webservers nicht blockieren
        log.error("Konfiguration konnte nicht erzeugt werden: %s", exc)
    sys.exit(0)
