"""Im Webinterface einstellbare Standardwerte, gespeichert als JSON im Config-Ordner."""

import json
import os
import string
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, field_validator

from app.settings import Settings

Format = Literal["mp3", "flac"]
FlacQuality = Literal[6, 7, 27]

# Gleiche Standardmuster wie qobuz-dl
DEFAULT_FOLDER = "{artist} - {album} ({year}) [{bit_depth}B-{sampling_rate}kHz]"
DEFAULT_TRACK = "{tracknumber}. {tracktitle}"

# Platzhalter, die qobuz-dl für Alben UND Einzeltitel kennt (sonst KeyError)
FOLDER_KEYS = {"artist", "album", "year", "bit_depth", "sampling_rate"}
TRACK_KEYS = {
    "artist", "albumartist", "tracktitle", "tracknumber", "version",
    "bit_depth", "sampling_rate",
}
FORBIDDEN_CHARS = set(':<>"|?*\\')


def qobuz_quality(fmt: str, quality: int) -> int:
    """Format + FLAC-Qualität → qobuz-dl-Qualitätsstufe (5, 6, 7, 27)."""
    return 5 if fmt == "mp3" else quality


def _check_pattern(pattern: str, allowed: set[str], *, allow_slash: bool) -> str:
    pattern = pattern.strip()
    if not pattern:
        raise ValueError("Muster darf nicht leer sein.")
    try:
        keys = {f for _, f, _, _ in string.Formatter().parse(pattern) if f is not None}
    except ValueError as exc:
        raise ValueError(f"Ungültiges Muster: {exc}") from exc
    unknown = keys - allowed
    if unknown or "" in keys:
        raise ValueError(
            f"Unbekannte Platzhalter: {', '.join(sorted(unknown)) or '{}'}. "
            f"Erlaubt: {', '.join(sorted(allowed))}"
        )
    forbidden = FORBIDDEN_CHARS if allow_slash else FORBIDDEN_CHARS | {"/"}
    bad = forbidden & set(pattern)
    if bad:
        raise ValueError(f"Unerlaubte Zeichen: {' '.join(sorted(bad))}")
    if allow_slash and (pattern.startswith("/") or ".." in pattern.split("/")):
        raise ValueError("Ordnermuster muss relativ bleiben (kein führendes / und kein ..).")
    return pattern


class Preferences(BaseModel):
    format: Format = "flac"
    quality: FlacQuality = 6
    target_dir: str = ""
    folder_format: str = DEFAULT_FOLDER
    track_format: str = DEFAULT_TRACK

    @field_validator("target_dir")
    @classmethod
    def _target(cls, v: str) -> str:
        v = v.strip().strip("/")
        if ".." in v.split("/"):
            raise ValueError("Zielordner darf kein .. enthalten.")
        return v

    @field_validator("folder_format")
    @classmethod
    def _folder(cls, v: str) -> str:
        return _check_pattern(v, FOLDER_KEYS, allow_slash=True)

    @field_validator("track_format")
    @classmethod
    def _track(cls, v: str) -> str:
        return _check_pattern(v, TRACK_KEYS, allow_slash=False)


def _path(settings: Settings) -> Path:
    return settings.config_dir / "web-settings.json"


def initial(settings: Settings) -> Preferences:
    q = settings.default_quality
    if q == 5:
        return Preferences(format="mp3")
    return Preferences(quality=q if q in (6, 7, 27) else 6)


def load(settings: Settings) -> Preferences:
    path = _path(settings)
    if not path.is_file():
        return initial(settings)
    try:
        return Preferences.model_validate_json(path.read_text())
    except (ValueError, OSError):
        return initial(settings)


def save(settings: Settings, prefs: Preferences) -> None:
    path = _path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(prefs.model_dump(), indent=2, ensure_ascii=False))
    os.replace(tmp, path)
