"""Download-Warteschlange: ruft qobuz-dl als Subprozess auf, ein Job nach dem anderen."""

import asyncio
import codecs
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from app.preferences import Preferences, qobuz_quality
from app.settings import Settings
from app.storage import check_target, resolve

ALLOWED_URL = re.compile(
    r"^https://(open|play|www)\.qobuz\.com/\S+$|^https://(www\.)?last\.fm/\S+$"
)
LOG_LINES = 200
READ_CHUNK = 4096
# Farbcodes von colorama/tqdm aus der Ausgabe entfernen
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

# Zeilen, an denen qobuz-dl erkennbar ist (siehe qobuz_dl/core.py, downloader.py)
NEW_TRACK = re.compile(r" /// .*\.\d+\.tmp$")  # fertiger Fortschrittsbalken eines Titels
EXISTING = re.compile(r"^(?!(cover\.jpg|booklet\.pdf) ).+ was already downloaded$")
RELEASE_IN_DB = re.compile(r"was already downloaded according to the local database")
UNAVAILABLE = re.compile(r"Track not available for download")


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    skipped = "skipped"  # fehlerfrei, aber nichts Neues geladen
    failed = "failed"


@dataclass
class Summary:
    new: int = 0
    existing: int = 0
    unavailable: int = 0
    releases_in_db: int = 0

    def feed(self, line: str) -> None:
        if NEW_TRACK.search(line):
            self.new += 1
        elif RELEASE_IN_DB.search(line):
            self.releases_in_db += 1
        elif EXISTING.search(line):
            self.existing += 1
        elif UNAVAILABLE.search(line):
            self.unavailable += 1

    @property
    def nothing_new(self) -> bool:
        return self.new == 0 and (self.existing or self.releases_in_db or self.unavailable) > 0


@dataclass
class Job:
    url: str
    options: Preferences
    # Datenbank von qobuz-dl ignorieren (--no-db): schon geladene Alben erneut holen
    redownload: bool = False
    summary: Summary = field(default_factory=Summary)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: JobStatus = JobStatus.queued
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    return_code: int | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=LOG_LINES))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "format": self.options.format,
            "quality": self.options.quality,
            "target_dir": self.options.target_dir,
            "redownload": self.redownload,
            "status": self.status.value,
            "summary": {
                "new": self.summary.new,
                "existing": self.summary.existing,
                "unavailable": self.summary.unavailable,
                "releases_in_db": self.summary.releases_in_db,
            },
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "return_code": self.return_code,
            "log": list(self.log),
        }


def validate(url: str) -> None:
    if not ALLOWED_URL.match(url.strip()):
        raise ValueError("Nur Qobuz- oder last.fm-URLs (https) sind erlaubt.")


def build_command(settings: Settings, job: Job) -> list[str]:
    # Liste statt Shell-String: keine Shell-Injection möglich
    o = job.options
    cmd = [
        settings.qobuz_dl_bin,
        "dl",
        job.url,
        "-q",
        str(qobuz_quality(o.format, o.quality)),
        "-d",
        str(resolve(settings.shares_dir, o.target_dir)),
        "-ff",
        o.folder_format,
        "-tf",
        o.track_format,
    ]
    if job.redownload:
        cmd.append("--no-db")
    return cmd


async def read_lines(stream: asyncio.StreamReader):
    """Ausgabe in Blöcken lesen und in Zeilen zerlegen.

    tqdm überschreibt seinen Fortschrittsbalken mit \\r und schreibt erst am Ende
    eines Titels \\n. Zeilenweises Lesen würde bei langen Titeln am 64-KB-Limit
    von StreamReader.readline scheitern; hier bleibt nur der letzte Stand übrig.
    """
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buf = ""
    while chunk := await stream.read(READ_CHUNK):
        buf += decoder.decode(chunk)  # Umlaute können über Blockgrenzen gehen
        *lines, buf = buf.split("\n")
        for line in lines:
            yield line.split("\r")[-1]
        buf = buf.split("\r")[-1] if "\r" in buf else buf[-READ_CHUNK:]
    if buf:
        yield buf.split("\r")[-1]


class JobManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._worker: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def submit(self, url: str, options: Preferences, redownload: bool = False) -> Job:
        url = url.strip()
        validate(url)
        check_target(self.settings.shares_dir, options.target_dir)
        job = Job(url=url, options=options, redownload=redownload)
        self.jobs[job.id] = job
        self._queue.put_nowait(job)
        return job

    def list(self) -> list[Job]:
        return sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)

    async def _run_forever(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self.run(job)
            finally:
                self._queue.task_done()

    async def run(self, job: Job) -> None:
        job.status = JobStatus.running
        try:
            resolve(self.settings.shares_dir, job.options.target_dir).mkdir(
                parents=True, exist_ok=True
            )
            proc = await asyncio.create_subprocess_exec(
                *build_command(self.settings, job),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            async for raw in read_lines(proc.stdout):
                line = ANSI.sub("", raw).rstrip()
                if line:
                    job.log.append(line)
                    job.summary.feed(line)
            job.return_code = await proc.wait()
            if job.return_code != 0:
                job.status = JobStatus.failed
            elif job.summary.nothing_new:
                job.status = JobStatus.skipped
            else:
                job.status = JobStatus.done
        except Exception as exc:
            job.log.append(f"Fehler: {exc}")
            job.status = JobStatus.failed
        finally:
            job.finished_at = datetime.now(timezone.utc)
