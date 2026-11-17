"""Download-Warteschlange: ruft qobuz-dl als Subprozess auf, ein Job nach dem anderen."""

import asyncio
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
# Farbcodes von colorama/tqdm aus der Ausgabe entfernen
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


@dataclass
class Job:
    url: str
    options: Preferences
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
            "status": self.status.value,
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
    return [
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

    def submit(self, url: str, options: Preferences) -> Job:
        url = url.strip()
        validate(url)
        check_target(self.settings.shares_dir, options.target_dir)
        job = Job(url=url, options=options)
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
            async for raw in proc.stdout:
                # tqdm nutzt \r für Fortschrittsbalken, nur der letzte Stand zählt
                line = ANSI.sub("", raw.decode(errors="replace")).split("\r")[-1].rstrip()
                if line:
                    job.log.append(line)
            job.return_code = await proc.wait()
            job.status = JobStatus.done if job.return_code == 0 else JobStatus.failed
        except Exception as exc:
            job.log.append(f"Fehler: {exc}")
            job.status = JobStatus.failed
        finally:
            job.finished_at = datetime.now(timezone.utc)
