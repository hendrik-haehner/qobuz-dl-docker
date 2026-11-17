import os

import pytest

from app import storage
from app.storage import StorageError


@pytest.fixture
def root(tmp_path):
    """Wie /volume1 auf einer Synology: Freigaben plus Systemordner."""
    r = tmp_path / "shares"
    for d in ("music/Rock", "music/Jazz/Bebop", "Downloads", "@eaDir", "@docker", ".hidden", "#recycle"):
        (r / d).mkdir(parents=True)
    (r / "datei.flac").write_text("")
    return r


def test_root_lists_shares_hides_system_dirs(root):
    data = storage.list_dirs(root, "")
    assert data["is_root"] is True
    assert data["dirs"] == ["Downloads", "music"]
    assert data["writable"] is False  # direkt nach /shares wird nie geschrieben
    assert [s["name"] for s in data["shares"]] == ["Downloads", "music"]
    assert all(s["mounted"] and s["writable"] for s in data["shares"])


def test_list_inside_share(root):
    data = storage.list_dirs(root, "/music/")
    assert (data["path"], data["is_root"], data["dirs"]) == ("music", False, ["Jazz", "Rock"])
    assert storage.list_dirs(root, "music/Jazz")["dirs"] == ["Bebop"]


@pytest.mark.parametrize("path", ["..", "../..", "music/../../", "nicht-da"])
def test_list_rejects(root, path):
    with pytest.raises(StorageError):
        storage.list_dirs(root, path)


def test_symlink_inside_root_ok_outside_rejected(root, tmp_path):
    os.symlink(root / "music" / "Jazz", root / "music" / "link-innen")
    os.symlink(tmp_path, root / "music" / "link-aussen")
    assert storage.list_dirs(root, "music/link-innen")["dirs"] == ["Bebop"]
    with pytest.raises(StorageError):
        storage.list_dirs(root, "music/link-aussen")


def test_make_dir(root):
    assert storage.make_dir(root, "music/Jazz", "Cool Jazz") == "music/Jazz/Cool Jazz"
    assert (root / "music" / "Jazz" / "Cool Jazz").is_dir()
    assert storage.make_dir(root, "music/Jazz", "Cool Jazz") == "music/Jazz/Cool Jazz"


def test_make_dir_not_in_root(root):
    with pytest.raises(StorageError, match="docker-compose"):
        storage.make_dir(root, "", "NeueFreigabe")
    assert not (root / "NeueFreigabe").exists()


@pytest.mark.parametrize("name", ["", "..", ".", "a/b", ".versteckt", "@eaDir", "a:b"])
def test_make_dir_rejects_names(root, name):
    with pytest.raises(StorageError):
        storage.make_dir(root, "music", name)


def test_make_dir_rejects_parent_outside(root):
    with pytest.raises(StorageError):
        storage.make_dir(root, "..", "x")


def test_check_target(root):
    assert storage.check_target(root, "music/Rock") == (root / "music" / "Rock").resolve()
    # Unterordner darf noch fehlen (wird beim Download angelegt), die Freigabe nicht
    assert storage.check_target(root, "music/Neu/Album").name == "Album"
    with pytest.raises(StorageError, match="Freigabe wählen"):
        storage.check_target(root, "")
    with pytest.raises(StorageError, match="gibt es nicht"):
        storage.check_target(root, "Video/x")


def test_unmounted_share_is_rejected(root, monkeypatch):
    """Ohne Mount lägen die Dateien im Container und wären beim Update weg."""
    monkeypatch.delenv("ALLOW_UNMOUNTED_SHARES")
    # tmp_path liegt auf demselben Dateisystem wie "/" → gilt als nicht eingebunden
    if os.stat(root).st_dev != os.stat("/").st_dev:
        pytest.skip("tmp liegt hier auf einem eigenen Dateisystem")
    assert storage.is_mounted(root / "music") is False
    assert storage.list_dirs(root, "")["shares"][0]["mounted"] is False
    assert storage.list_dirs(root, "music")["mounted"] is False
    with pytest.raises(StorageError, match="kein eingebundener NAS-Ordner"):
        storage.check_target(root, "music/Rock")
    assert storage.default_target(root) == ""


def test_is_mounted_detects_other_device(root, monkeypatch):
    monkeypatch.delenv("ALLOW_UNMOUNTED_SHARES")
    # nur "music" liegt auf einem anderen Gerät (NAS-Mount), alles andere im Container
    monkeypatch.setattr(
        storage, "_device", lambda p: 2 if str(p) != "/" and "music" in str(p) else 1
    )
    assert storage.is_mounted(root / "music") is True
    assert storage.is_mounted(root / "Downloads") is False
    assert storage.default_target(root) == "music"
    assert storage.check_target(root, "music/Rock").name == "Rock"
    with pytest.raises(StorageError, match="kein eingebundener"):
        storage.check_target(root, "Downloads")


def test_default_target(root, tmp_path):
    assert storage.default_target(root) == ""  # zwei Freigaben → keine Vorauswahl
    single = tmp_path / "single"
    (single / "music").mkdir(parents=True)
    assert storage.default_target(single) == "music"


def test_permission_error_names_container_user(root, monkeypatch):
    def denied(path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(storage.os, "scandir", denied)
    with pytest.raises(StorageError, match=r"Kein Zugriff: Der Container \(Benutzer \d+:\d+\)"):
        storage.list_dirs(root, "music")


def test_root_reports_access_and_container_user(root):
    data = storage.list_dirs(root, "")
    assert (data["uid"], data["gid"]) == (os.getuid(), os.getgid())
    assert all(s["readable"] for s in data["shares"])
