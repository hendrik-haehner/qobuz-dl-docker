import os

import pytest

from app import storage
from app.storage import StorageError


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "music"
    for d in ("Rock", "abba", "Jazz/Bebop", "@eaDir", ".hidden", "#recycle"):
        (r / d).mkdir(parents=True)
    (r / "datei.flac").write_text("")
    return r


def test_list_root_hides_system_dirs(root):
    data = storage.list_dirs(root, "")
    assert data["path"] == ""
    assert data["dirs"] == ["abba", "Jazz", "Rock"]
    assert data["writable"] is True


def test_list_subdir(root):
    assert storage.list_dirs(root, "/Jazz/")["dirs"] == ["Bebop"]
    assert storage.list_dirs(root, "Jazz")["path"] == "Jazz"


@pytest.mark.parametrize("path", ["..", "../..", "Jazz/../../", "nicht-da"])
def test_list_rejects(root, path):
    with pytest.raises(StorageError):
        storage.list_dirs(root, path)


def test_symlink_inside_root_ok_outside_rejected(root, tmp_path):
    os.symlink(root / "Jazz", root / "link-innen")
    os.symlink(tmp_path, root / "link-aussen")
    assert storage.list_dirs(root, "link-innen")["dirs"] == ["Bebop"]
    with pytest.raises(StorageError):
        storage.list_dirs(root, "link-aussen")


def test_make_dir(root):
    assert storage.make_dir(root, "Jazz", "Cool Jazz") == "Jazz/Cool Jazz"
    assert (root / "Jazz" / "Cool Jazz").is_dir()
    # schon vorhanden ist kein Fehler
    assert storage.make_dir(root, "Jazz", "Cool Jazz") == "Jazz/Cool Jazz"


@pytest.mark.parametrize("name", ["", "..", ".", "a/b", ".versteckt", "a:b"])
def test_make_dir_rejects_names(root, name):
    with pytest.raises(StorageError):
        storage.make_dir(root, "", name)


def test_make_dir_rejects_parent_outside(root):
    with pytest.raises(StorageError):
        storage.make_dir(root, "..", "x")
