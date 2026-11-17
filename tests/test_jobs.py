import asyncio
from pathlib import Path

import pytest

from app.jobs import Job, JobManager, JobStatus, build_command, validate
from app.preferences import Preferences
from app.settings import Settings
from app.storage import StorageError
from tests.conftest import write_fake_bin

URL = "https://open.qobuz.com/album/a"


def make_settings(tmp_path: Path, bin_path: str = "qobuz-dl") -> Settings:
    (tmp_path / "dl").mkdir(exist_ok=True)
    return Settings(
        shares_dir=tmp_path / "dl",
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
    validate(url)


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
        validate(url)


def test_build_command_flac(tmp_path):
    s = make_settings(tmp_path)
    opts = Preferences(format="flac", quality=27, target_dir="Hi-Res",
                       folder_format="{artist}/{album}", track_format="{tracknumber} {tracktitle}")
    cmd = build_command(s, Job(url=URL, options=opts))
    assert cmd == [
        "qobuz-dl", "dl", URL, "-q", "27", "-d", str((s.shares_dir / "Hi-Res").resolve()),
        "-ff", "{artist}/{album}", "-tf", "{tracknumber} {tracktitle}",
    ]


def test_build_command_mp3_ignores_flac_quality(tmp_path):
    s = make_settings(tmp_path)
    cmd = build_command(s, Job(url=URL, options=Preferences(format="mp3", quality=27)))
    assert cmd[cmd.index("-q") + 1] == "5"
    assert cmd[cmd.index("-d") + 1] == str(s.shares_dir.resolve())


@pytest.mark.parametrize("code,status", [(0, JobStatus.done), (1, JobStatus.failed)])
def test_run_job(tmp_path, code, status):
    manager = JobManager(make_settings(tmp_path, write_fake_bin(tmp_path, code)))
    job = Job(url=URL, options=Preferences(target_dir="neu/unterordner"))
    asyncio.run(manager.run(job))
    assert job.status == status
    assert job.return_code == code
    assert list(job.log)[:2] == [f"Downloading {URL}", "100%"]
    # Zielordner wird bei Bedarf angelegt
    assert (tmp_path / "dl" / "neu" / "unterordner").is_dir()


def test_missing_binary_marks_failed(tmp_path):
    manager = JobManager(make_settings(tmp_path, str(tmp_path / "missing")))
    job = Job(url=URL, options=Preferences())
    asyncio.run(manager.run(job))
    assert job.status == JobStatus.failed


def test_submit_rejects_symlink_escape(tmp_path):
    s = make_settings(tmp_path)
    (s.shares_dir / "raus").symlink_to(tmp_path)
    manager = JobManager(s)
    with pytest.raises(StorageError):
        manager.submit(URL, Preferences(target_dir="raus"))
