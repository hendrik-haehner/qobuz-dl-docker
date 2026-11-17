"""Ordner im Musik-Root (z. B. NAS-Freigabe) auflisten und anlegen, ohne aus dem Root auszubrechen."""

import os
from pathlib import Path

# Systemordner von Synology/QNAP/macOS ausblenden
HIDDEN = {"@eaDir", "#recycle", "@Recycle", "#snapshot", "@Recently-Snapshot", "lost+found"}
FORBIDDEN_NAME_CHARS = set('/\\:<>"|?*')


class StorageError(ValueError):
    pass


def resolve(root: Path, rel: str) -> Path:
    """Relativen Pfad auflösen; Fehler, wenn er (auch per Symlink) aus dem Root führt."""
    root_real = Path(os.path.realpath(root))
    target = Path(os.path.realpath(root_real / rel.strip().strip("/")))
    if target != root_real and root_real not in target.parents:
        raise StorageError("Pfad liegt außerhalb des Musikordners.")
    return target


def relative(root: Path, path: Path) -> str:
    rel = path.relative_to(Path(os.path.realpath(root))).as_posix()
    return "" if rel == "." else rel


def list_dirs(root: Path, rel: str) -> dict:
    path = resolve(root, rel)
    if not path.is_dir():
        raise StorageError("Ordner existiert nicht.")
    try:
        names = sorted(
            (e.name for e in os.scandir(path)
             if e.is_dir() and not e.name.startswith(".") and e.name not in HIDDEN),
            key=str.casefold,
        )
    except PermissionError as exc:
        raise StorageError("Keine Leserechte für diesen Ordner.") from exc
    return {
        "path": relative(root, path),
        "dirs": names,
        "writable": os.access(path, os.W_OK),
    }


def make_dir(root: Path, parent: str, name: str) -> str:
    name = name.strip()
    if not name or name in (".", "..") or FORBIDDEN_NAME_CHARS & set(name) or name.startswith("."):
        raise StorageError("Ungültiger Ordnername.")
    target = resolve(root, parent) / name
    try:
        target.mkdir(exist_ok=True)
    except PermissionError as exc:
        raise StorageError("Keine Schreibrechte in diesem Ordner.") from exc
    except FileNotFoundError as exc:
        raise StorageError("Übergeordneter Ordner existiert nicht.") from exc
    return relative(root, target)
