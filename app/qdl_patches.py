"""Kleine Korrekturen an qobuz-dl, die der Runner vor jedem Download einspielt.

`/` in Namen: qobuz-dl setzt Ordnernamen per `folder_format.format(...)` zusammen
und behandelt danach jedes `/` als Pfadtrenner. Aus dem Interpreten „AC/DC“
würde so der Ordner `AC` mit Unterordner `DC`. Wir ersetzen `/` und `\\` in den
Werten (nicht im Muster) durch `-`. Die Tags in den Dateien bleiben unverändert,
die setzt qobuz-dl aus den Originaldaten.
"""

from qobuz_dl.downloader import Download

SEPARATOR_REPLACEMENT = "-"
# Liefern die Werte für {artist}, {album}, {tracktitle} usw.
NAME_HELPERS = ("_get_album_attr", "_get_track_attr", "_get_filename_attr")


def clean_value(value):
    if isinstance(value, str):
        return value.replace("/", SEPARATOR_REPLACEMENT).replace("\\", SEPARATOR_REPLACEMENT)
    return value


def _wrap(original):
    def wrapper(*args, **kwargs):
        return {key: clean_value(val) for key, val in original(*args, **kwargs).items()}

    wrapper.__wrapped__ = original
    return staticmethod(wrapper)


def install_name_fix() -> None:
    for name in NAME_HELPERS:
        current = getattr(Download, name)  # bei staticmethod: die Funktion selbst
        if not hasattr(current, "__wrapped__"):  # nicht doppelt einspielen
            setattr(Download, name, _wrap(current))
