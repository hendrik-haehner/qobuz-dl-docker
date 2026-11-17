"""NAS-Freigaben unter dem Freigaben-Root (/shares) verwalten.

Jeder Ordner direkt unter /shares ist eine Freigabe, die in docker-compose.yml
eingebunden wird (z. B. /volume1/music:/shares/music). Heruntergeladen wird
immer in eine Freigabe oder einen Unterordner davon, nie direkt nach /shares:
Was dort landet, läge im Container und wäre beim nächsten Update weg.
"""

import os
from pathlib import Path

# Systemordner von Synology/QNAP/macOS ausblenden ("@eaDir", "#recycle", "@docker", ...)
HIDDEN = {"lost+found", "System Volume Information", "$RECYCLE.BIN"}
HIDDEN_PREFIXES = (".", "@", "#")
FORBIDDEN_NAME_CHARS = set('/\\:<>"|?*')


class StorageError(ValueError):
    pass


def _visible(name: str) -> bool:
    return not name.startswith(HIDDEN_PREFIXES) and name not in HIDDEN


def _root(root: Path) -> Path:
    return Path(os.path.realpath(root))


def resolve(root: Path, rel: str) -> Path:
    """Relativen Pfad auflösen; Fehler, wenn er (auch per Symlink) aus dem Root führt."""
    root_real = _root(root)
    target = Path(os.path.realpath(root_real / rel.strip().strip("/")))
    if target != root_real and root_real not in target.parents:
        raise StorageError("Pfad liegt außerhalb der Freigaben.")
    return target


def relative(root: Path, path: Path) -> str:
    rel = path.relative_to(_root(root)).as_posix()
    return "" if rel == "." else rel


def _device(path) -> int:
    return os.stat(path).st_dev


def is_mounted(path: Path) -> bool:
    """Liegt der Ordner auf einem eingebundenen Dateisystem (NAS) statt im Container?

    Vergleicht das Gerät mit dem des Container-Wurzeldateisystems. Das klappt
    für einzelne Freigaben (/volume1/music:/shares/music) ebenso wie für ein
    ganzes Volume (/volume1:/shares) und für NFS/SMB-Volumes.
    """
    if os.environ.get("ALLOW_UNMOUNTED_SHARES") == "1":
        return True
    try:
        return _device(path) != _device("/")
    except OSError:
        return False


def shares(root: Path) -> list[dict]:
    root_real = _root(root)
    if not root_real.is_dir():
        return []
    result = []
    for entry in sorted(os.scandir(root_real), key=lambda e: e.name.casefold()):
        if entry.is_dir() and _visible(entry.name):
            path = Path(entry.path)
            result.append({
                "name": entry.name,
                "mounted": is_mounted(path),
                "readable": os.access(path, os.R_OK | os.X_OK),
                "writable": os.access(path, os.W_OK | os.X_OK),
            })
    return result


def check_target(root: Path, rel: str) -> Path:
    """Prüft einen Speicherort für Downloads und gibt den absoluten Pfad zurück."""
    target = resolve(root, rel)
    rel_real = relative(root, target)
    if not rel_real:
        raise StorageError("Bitte einen Speicherort in einer Freigabe wählen.")
    share = rel_real.split("/")[0]
    share_path = _root(root) / share
    if not share_path.is_dir():
        raise StorageError(
            f"Freigabe „{share}“ gibt es nicht. Ist sie in docker-compose.yml eingebunden?"
        )
    if not is_mounted(share_path):
        raise StorageError(
            f"„{share}“ ist kein eingebundener NAS-Ordner. Die Dateien lägen nur im "
            "Container. Freigabe in docker-compose.yml einbinden (siehe README)."
        )
    return target


def default_target(root: Path) -> str:
    """Gibt es genau eine eingebundene Freigabe, ist sie der Standard-Speicherort."""
    mounted = [s["name"] for s in shares(root) if s["mounted"]]
    return mounted[0] if len(mounted) == 1 else ""


def list_dirs(root: Path, rel: str) -> dict:
    path = resolve(root, rel)
    if not path.is_dir():
        raise StorageError("Ordner existiert nicht.")
    rel_real = relative(root, path)
    if not rel_real:
        share_list = shares(root)
        return {
            "path": "",
            "is_root": True,
            "dirs": [s["name"] for s in share_list],
            "shares": share_list,
            "writable": False,
            # Mit dieser ID greift der Container zu (PUID/PGID aus .env)
            "uid": os.getuid(),
            "gid": os.getgid(),
        }
    try:
        names = sorted(
            (e.name for e in os.scandir(path) if e.is_dir() and _visible(e.name)),
            key=str.casefold,
        )
    except PermissionError as exc:
        raise StorageError(
            f"Kein Zugriff: Der Container (Benutzer {os.getuid()}:{os.getgid()}) darf "
            f"„{rel_real}“ nicht lesen. Rechte der Freigabe für diesen Benutzer oder "
            "PUID/PGID in .env prüfen."
        ) from exc
    share_path = _root(root) / rel_real.split("/")[0]
    return {
        "path": rel_real,
        "is_root": False,
        "dirs": names,
        "mounted": is_mounted(share_path),
        "writable": os.access(path, os.W_OK),
    }


def make_dir(root: Path, parent: str, name: str) -> str:
    name = name.strip()
    if not name or name in (".", "..") or FORBIDDEN_NAME_CHARS & set(name) or not _visible(name):
        raise StorageError("Ungültiger Ordnername.")
    parent_path = resolve(root, parent)
    if not relative(root, parent_path):
        raise StorageError(
            "Neue Freigaben werden in docker-compose.yml eingebunden, nicht hier. "
            "Bitte zuerst eine Freigabe öffnen."
        )
    target = parent_path / name
    try:
        target.mkdir(exist_ok=True)
    except PermissionError as exc:
        raise StorageError("Keine Schreibrechte in diesem Ordner.") from exc
    except FileNotFoundError as exc:
        raise StorageError("Übergeordneter Ordner existiert nicht.") from exc
    return relative(root, target)
