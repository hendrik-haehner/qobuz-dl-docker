from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolierter HOME (qobuz-dl-Config) und Musik-Root."""
    home = tmp_path / "home"
    music = tmp_path / "music"
    music.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHARES_DIR", str(music))
    monkeypatch.delenv("QOBUZ_DEFAULT_QUALITY", raising=False)
    # Testordner sind nie NAS-Mounts; die Prüfung wird in test_storage gezielt getestet
    monkeypatch.setenv("ALLOW_UNMOUNTED_SHARES", "1")
    return {"home": home, "music": music, "config": home / ".config" / "qobuz-dl"}


@pytest.fixture
def configured(env):
    env["config"].mkdir(parents=True)
    (env["config"] / "config.ini").write_text("[DEFAULT]\n")
    return env


@pytest.fixture(autouse=True)
def _restore_qobuz_dl():
    """Der Runner patcht qobuz-dl global; nach jedem Test den Originalzustand herstellen."""
    from qobuz_dl import qopy
    from qobuz_dl.downloader import Download

    from app import qdl_patches

    helpers = {n: Download.__dict__[n] for n in qdl_patches.NAME_HELPERS}
    auth = qopy.Client.auth
    yield
    for name, value in helpers.items():
        setattr(Download, name, value)
    qopy.Client.auth = auth


@pytest.fixture(autouse=True)
def _defaults(monkeypatch):
    monkeypatch.setenv("ALLOW_UNMOUNTED_SHARES", "1")
    monkeypatch.delenv("WEB_PASSWORD", raising=False)
    from app import auth
    auth.reset_failures()


def write_fake_bin(dir_: Path, code: int = 0) -> str:
    """Ersatz für qobuz-dl: gibt seine Argumente aus."""
    script = dir_ / "fake-qobuz-dl"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('\\x1b[33mDownloading', sys.argv[2])\n"
        "print('50%\\r100%')\n"
        "print('ARGS', '|'.join(sys.argv[1:]))\n"
        f"sys.exit({code})\n"
    )
    script.chmod(0o755)
    return str(script)
