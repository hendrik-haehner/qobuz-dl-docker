import asyncio
import sys
from pathlib import Path

import pytest

from app.jobs import Job, JobManager, JobStatus, build_command, validate
from app.settings import Settings


def make_settings(tmp_path: Path, bin_path: str = "qobuz-dl") -> Settings:
    return Settings(
        download_dir=tmp_path / "dl",
        config_dir=tmp_path / "cfg",
        qobuz_dl_bin=bin_path,
        default_quality=6,
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://open.qobuz.com/album/abc123",
        "https://play.qobuz.com/playlist/42",
        "https://www.qobuz.com/de-de/album/x/y",
        "https://www.last.fm/user/someone/playlists/1",
    ],
)
def test_validate_accepts(url):
    validate(url, 27)


@pytest.mark.parametrize(
    "url",
    [
        "http://open.qobuz.com/album/abc",
        "https://evil.example.com/qobuz.com",
        "https://open.qobuz.com/album/a b",
        "--help",
        "",
    ],
)
def test_validate_rejects_url(url):
    with pytest.raises(ValueError):
        validate(url, 6)


def test_validate_rejects_quality():
    with pytest.raises(ValueError):
        validate("https://open.qobuz.com/album/a", 8)


def test_build_command(tmp_path):
    s = make_settings(tmp_path)
    job = Job(url="https://open.qobuz.com/album/a", quality=7)
    assert build_command(s, job) == [
        "qobuz-dl", "dl", "https://open.qobuz.com/album/a", "-q", "7", "-d", str(s.download_dir),
    ]


def _fake_bin(tmp_path: Path, code: int) -> str:
    script = tmp_path / "fake-qobuz-dl"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "print('\\x1b[33mDownloading', sys.argv[2])\n"
        "print('50%\\r100%')\n"
        f"sys.exit({code})\n"
    )
    script.chmod(0o755)
    return str(script)


@pytest.mark.parametrize("code,status", [(0, JobStatus.done), (1, JobStatus.failed)])
def test_run_job(tmp_path, code, status):
    manager = JobManager(make_settings(tmp_path, _fake_bin(tmp_path, code)))
    job = Job(url="https://open.qobuz.com/album/a", quality=6)
    asyncio.run(manager.run(job))
    assert job.status == status
    assert job.return_code == code
    assert list(job.log) == ["Downloading https://open.qobuz.com/album/a", "100%"]


def test_missing_binary_marks_failed(tmp_path):
    manager = JobManager(make_settings(tmp_path, str(tmp_path / "missing")))
    job = Job(url="https://open.qobuz.com/album/a", quality=6)
    asyncio.run(manager.run(job))
    assert job.status == JobStatus.failed
