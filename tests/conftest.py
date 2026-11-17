from pathlib import Path

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolierter HOME (qobuz-dl-Config) und Musik-Root."""
    home = tmp_path / "home"
    music = tmp_path / "music"
    music.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("DOWNLOAD_DIR", str(music))
    monkeypatch.delenv("QOBUZ_DEFAULT_QUALITY", raising=False)
    return {"home": home, "music": music, "config": home / ".config" / "qobuz-dl"}


@pytest.fixture
def configured(env):
    env["config"].mkdir(parents=True)
    (env["config"] / "config.ini").write_text("[DEFAULT]\n")
    return env


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
