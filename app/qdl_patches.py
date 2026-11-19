"""Kleine Korrekturen an qobuz-dl, die der Runner vor jedem Download einspielt.

`/` in Namen: qobuz-dl setzt Ordnernamen per `folder_format.format(...)` zusammen
und behandelt danach jedes `/` als Pfadtrenner. Aus dem Interpreten „AC/DC“
würde so der Ordner `AC` mit Unterordner `DC`. Wir ersetzen `/` und `\\` in den
Werten (nicht im Muster) durch `-`. Die Tags in den Dateien bleiben unverändert,
die setzt qobuz-dl aus den Originaldaten.

Name für die Download-Liste: qobuz-dl gibt bei Alben nur den Titel ohne
Interpret aus. Dieselben Hilfsfunktionen kennen beides, darum melden sie es
in einer eigenen Zeile (MARKER + JSON), die die Download-Liste auswertet.
"""

import json
import sys

from qobuz_dl.downloader import Download

MARKER = "qdl-web: "
# Diese Hilfsfunktionen laufen einmal pro Album bzw. Einzeltitel
ANNOUNCE = {"_get_album_attr": "album", "_get_track_attr": "tracktitle"}

SEPARATOR_REPLACEMENT = "-"
# Liefern die Werte für {artist}, {album}, {tracktitle} usw.
NAME_HELPERS = ("_get_album_attr", "_get_track_attr", "_get_filename_attr")


def clean_value(value):
    if isinstance(value, str):
        return value.replace("/", SEPARATOR_REPLACEMENT).replace("\\", SEPARATOR_REPLACEMENT)
    return value


def announce(attrs: dict, title_key: str) -> None:
    """Interpret und Titel (ungekürzt, mit „/“) für die Download-Liste ausgeben."""
    info = {"artist": attrs.get("artist") or "", "title": attrs.get(title_key) or ""}
    # stderr ist ungepuffert und landet wie die Meldungen von qobuz-dl im Job-Log
    sys.stderr.write(MARKER + json.dumps(info, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def _wrap(original, title_key=None):
    def wrapper(*args, **kwargs):
        attrs = original(*args, **kwargs)
        if title_key:
            announce(attrs, title_key)
        return {key: clean_value(val) for key, val in attrs.items()}

    wrapper.__wrapped__ = original
    return staticmethod(wrapper)


def install_name_fix() -> None:
    for name in NAME_HELPERS:
        current = getattr(Download, name)  # bei staticmethod: die Funktion selbst
        if not hasattr(current, "__wrapped__"):  # nicht doppelt einspielen
            setattr(Download, name, _wrap(current, ANNOUNCE.get(name)))
