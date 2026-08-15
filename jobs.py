"""An in-process job store, so a request does not have to stay open for the
several minutes a video takes to process.

State lives in memory: restarting the server forgets running jobs. That is the
right trade for a single-process app; a multi-worker deployment would need
Redis or a database here instead.
"""

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import config

STAGE_LABELS = {
    "queued": "Waiting for a free slot",
    "fetching_metadata": "Looking up the video",
    "fetching_captions": "Checking for existing captions",
    "downloading_audio": "Downloading audio",
    "transcribing": "Transcribing speech",
    "summarizing": "Writing the summary",
    "translating": "Translating",
    "synthesizing_audio": "Generating audio",
    "done": "Finished",
}


class Job:
    def __init__(self, job_id: str):
        self.id = job_id
        self.created_at = time.time()
        self._lock = threading.Lock()
        self._status = "queued"
        self._stage = "queued"
        self._progress = 0
        self._result: Optional[dict] = None
        self._error: Optional[dict] = None

    def set_stage(self, stage: str, progress: Optional[int] = None) -> None:
        with self._lock:
            self._status = "running"
            self._stage = stage
            if progress is not None:
                self._progress = max(self._progress, min(100, int(progress)))

    def set_progress(self, progress: float) -> None:
        with self._lock:
            self._progress = max(self._progress, min(100, int(progress)))

    def succeed(self, result: dict) -> None:
        with self._lock:
            self._status = "done"
            self._stage = "done"
            self._progress = 100
            self._result = result

    def fail(self, code: str, message: str) -> None:
        with self._lock:
            self._status = "error"
            self._error = {"code": code, "message": message}

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "job_id": self.id,
                "status": self._status,
                "stage": self._stage,
                "stage_label": STAGE_LABELS.get(self._stage, "Working"),
                "progress": self._progress,
                "result": self._result,
                "error": self._error,
            }

    @property
    def finished(self) -> bool:
        with self._lock:
            return self._status in ("done", "error")


class JobStore:
    def __init__(self, max_workers: int, ttl_seconds: int):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="job"
        )
        self._ttl = ttl_seconds
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, work: Callable[[Job], dict]) -> Job:
        self._purge()
        job = Job(uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job, work)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    @staticmethod
    def _run(job: Job, work: Callable[[Job], dict]) -> None:
        from errors import PipelineError

        try:
            job.succeed(work(job))
        except PipelineError as exc:
            job.fail(exc.code, exc.message)
        except Exception:
            traceback.print_exc()
            job.fail(
                "internal",
                "Something went wrong while processing this video. Please try again.",
            )

    def _purge(self) -> None:
        """Drop finished jobs past their TTL, and any media they produced."""
        cutoff = time.time() - self._ttl
        with self._lock:
            expired = [
                job_id
                for job_id, job in self._jobs.items()
                if job.created_at < cutoff and job.finished
            ]
            for job_id in expired:
                del self._jobs[job_id]

        if not config.MEDIA_DIR.exists():
            return
        for media_file in config.MEDIA_DIR.glob("*.mp3"):
            try:
                if media_file.stat().st_mtime < cutoff:
                    media_file.unlink()
            except OSError:
                pass
