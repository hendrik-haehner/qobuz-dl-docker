"""Erkennung von neu geladenen, vorhandenen und übersprungenen Titeln."""

import asyncio
import re
import sys
from pathlib import Path

import pytest

from app.jobs import Job, JobManager, JobStatus, Summary, build_command, read_lines
from app.preferences import Preferences
from app.settings import Settings

URL = "https://open.qobuz.com/album/a"

# Originaltexte aus qobuz_dl/core.py und downloader.py (Farbcodes wie im Original)
OFF, CYAN = "\x1b[2m", "\x1b[36m"
TRACK_BAR = CYAN + "{done}/{done} /// /shares/music/Daft Punk/Discovery/.{n:02}.tmp"
EXISTING = OFF + "One More Time was already downloaded"
COVER_EXISTING = OFF + "cover.jpg was already downloaded"
IN_DB = (OFF + "This release ID (abc) was already downloaded according to the local database."
         "\nUse the '--no-db' flag to bypass this.")
UNAVAILABLE = OFF + "Track not available for download"


def progress(n: int, steps: int = 3) -> str:
    """Wie tqdm: mehrere Stände mit \\r, am Ende \\n."""
    return "\r".join(TRACK_BAR.format(done=f"{i}M", n=n) for i in range(1, steps + 1)) + "\n"


def summarize(text: str) -> Summary:
    s = Summary()
    for line in text.split("\n"):
        line = line.split("\r")[-1]
        s.feed(re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line))
    return s


def test_summary_counts():
    s = summarize(progress(1) + EXISTING + "\n" + COVER_EXISTING + "\n" + progress(2) + UNAVAILABLE + "\n")
    assert (s.new, s.existing, s.unavailable, s.releases_in_db) == (2, 1, 1, 0)
    assert not s.nothing_new


@pytest.mark.parametrize("text", [EXISTING + "\n" + COVER_EXISTING, IN_DB, UNAVAILABLE])
def test_nothing_new(text):
    assert summarize(text + "\n").nothing_new


def test_cover_alone_is_not_a_track():
    s = summarize(COVER_EXISTING + "\n")
    assert s.existing == 0 and not s.nothing_new


class FakeStream:
    def __init__(self, data: bytes, chunk: int):
        self.data, self.chunk = data, chunk

    async def read(self, n):
        part, self.data = self.data[: min(n, self.chunk)], self.data[min(n, self.chunk):]
        return part


async def _collect(data: bytes, chunk: int = 4096):
    return [line async for line in read_lines(FakeStream(data, chunk))]


def test_read_lines_keeps_last_progress_state():
    lines = asyncio.run(_collect(b"a\rb\rc\nzweite\nrest"))
    assert lines == ["c", "zweite", "rest"]


def test_read_lines_long_progress_without_newline():
    # > 64 KB Fortschritt ohne \n: daran wäre readline() gescheitert
    bar = "\r".join(f"{i}K/9999K /// x/.01.tmp" for i in range(5000))
    assert len(bar) > 70_000
    lines = asyncio.run(_collect((bar + "\nfertig\n").encode()))
    assert lines == ["4999K/9999K /// x/.01.tmp", "fertig"]


def test_read_lines_umlaut_across_chunks():
    lines = asyncio.run(_collect("Müller – Grüße\n".encode(), chunk=1))
    assert lines == ["Müller – Grüße"]


def _fake(tmp_path: Path, output: str, code: int = 0) -> str:
    script = tmp_path / "fake-qobuz-dl"
    script.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        f"sys.stderr.write({output!r})\n"
        "print('ARGS', '|'.join(sys.argv[1:]))\n"
        f"sys.exit({code})\n"
    )
    script.chmod(0o755)
    return str(script)


def _run(tmp_path, output, code=0, redownload=False):
    (tmp_path / "dl" / "music").mkdir(parents=True, exist_ok=True)
    s = Settings(shares_dir=tmp_path / "dl", config_dir=tmp_path / "cfg",
                 qobuz_dl_bin=_fake(tmp_path, output, code), default_quality=6)
    job = Job(url=URL, options=Preferences(target_dir="music"), redownload=redownload)
    asyncio.run(JobManager(s).run(job))
    return job


@pytest.mark.parametrize(
    "output,code,status",
    [
        (progress(1) + progress(2), 0, JobStatus.done),
        (progress(1) + EXISTING + "\n", 0, JobStatus.done),  # teilweise neu
        (EXISTING + "\n" + EXISTING + "\n" + COVER_EXISTING + "\n", 0, JobStatus.skipped),
        (IN_DB + "\n", 0, JobStatus.skipped),
        (progress(1), 1, JobStatus.failed),
        ("", 0, JobStatus.done),  # keine erkennbaren Zeilen: nicht als übersprungen werten
    ],
)
def test_job_status_from_output(tmp_path, output, code, status):
    job = _run(tmp_path, output, code)
    assert job.status == status
    assert job.to_dict()["status"] == status.value


def test_redownload_adds_no_db(tmp_path):
    job = _run(tmp_path, "", redownload=True)
    args = next(line for line in job.log if line.startswith("ARGS")).split("|")
    assert args[-1] == "--no-db"
    assert job.to_dict()["redownload"] is True
    s = Settings(shares_dir=tmp_path / "dl", config_dir=tmp_path, qobuz_dl_bin="q", default_quality=6)
    assert "--no-db" not in build_command(s, Job(url=URL, options=Preferences(target_dir="music")))
