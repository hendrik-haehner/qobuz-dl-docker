import hashlib

import pytest

from app import qobuz_config


def test_build_config_matches_qobuz_dl_keys():
    cfg = qobuz_config.build_config(
        "a@b.c", "geheim", "123456789", ["s1", "s2"],
        download_dir="/downloads", quality=27, folder_format="F", track_format="T",
    )
    d = cfg["DEFAULT"]
    assert d["password"] == hashlib.md5(b"geheim").hexdigest()
    assert d["secrets"] == "s1,s2"
    assert d["default_quality"] == "27"
    # Diese Schlüssel liest qobuz_dl.cli.main() und bricht ab, wenn einer fehlt
    for key in ("default_folder", "default_limit", "no_m3u", "albums_only", "no_fallback",
                "og_cover", "embed_art", "no_cover", "no_database", "app_id",
                "smart_discography", "folder_format", "track_format"):
        assert key in d
    for key in ("no_m3u", "smart_discography"):
        assert cfg.getboolean("DEFAULT", key) is False


def test_build_config_rejects_quality():
    with pytest.raises(ValueError):
        qobuz_config.build_config("a", "b", "1", [], download_dir="/d", quality=3,
                                  folder_format="F", track_format="T")


def test_ensure_config_without_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("QOBUZ_EMAIL", raising=False)
    monkeypatch.delenv("QOBUZ_PASSWORD", raising=False)
    assert qobuz_config.ensure_config() is False
    assert not (tmp_path / ".config" / "qobuz-dl" / "config.ini").exists()


def test_ensure_config_keeps_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".config" / "qobuz-dl" / "config.ini"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("[DEFAULT]\nemail = x\n")
    monkeypatch.setenv("QOBUZ_EMAIL", "neu@b.c")
    monkeypatch.setenv("QOBUZ_PASSWORD", "pw")
    assert qobuz_config.ensure_config() is True
    assert "email = x" in cfg.read_text()
