"""In-memory batch jobs: many labels checked concurrently, results kept for a limited time.

Single-process only (TECHNICAL_DESIGN.md §7): jobs live in this process's memory, so the app
must run as one replica, and a restart loses unfinished batches.
"""

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import StrEnum

from app.batch.csv_io import ApplicationRow
from app.extract.base import ExtractionError, LabelExtractor
from app.imaging.prepare import ImageRejectedError
from app.rules.models import OverallStatus
from app.services.verify import LabelCheck, check_label

log = logging.getLogger(__name__)


class ItemState(StrEnum):
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"  # tried, couldn't be checked (bad image, model unavailable)
    SKIPPED = "skipped"  # never tried (bad row, missing image)


@dataclass
class BatchItem:
    index: int
    row_number: int | None
    filename: str
    brand_name: str
    state: ItemState = ItemState.WAITING
    check: LabelCheck | None = None
    problem: str | None = None
    retryable: bool = False

    @property
    def status(self) -> OverallStatus | None:
        return self.check.report.status if self.check else None


@dataclass
class Job:
    id: str
    items: list[BatchItem]
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    task: asyncio.Task[None] | None = None
    # Uploads of items that hit a temporary failure, kept so they can be retried.
    retry_work: dict[int, tuple[ApplicationRow, bytes]] = field(default_factory=dict)

    @property
    def done_count(self) -> int:
        return sum(item.state != ItemState.WAITING for item in self.items)

    @property
    def finished(self) -> bool:
        return self.finished_at is not None


def build_items(
    rows: list[ApplicationRow], images: dict[str, bytes]
) -> tuple[list[BatchItem], dict[int, tuple[ApplicationRow, bytes]]]:
    """Pair spreadsheet rows with uploaded images by filename (case-insensitive).

    Returns every item to show, and the work for the items that can actually be checked.
    """
    by_name = {name.lower(): data for name, data in images.items()}
    used: set[str] = set()
    items: list[BatchItem] = []
    work: dict[int, tuple[ApplicationRow, bytes]] = {}

    for row in rows:
        item = BatchItem(
            index=len(items),
            row_number=row.row_number,
            filename=row.image_filename,
            brand_name=row.application.brand_name if row.application else "",
        )
        key = row.image_filename.lower()
        if row.problem:
            item.state, item.problem = ItemState.SKIPPED, row.problem
        elif key in used:
            item.state, item.problem = ItemState.SKIPPED, "Another row already uses this image."
        elif key not in by_name:
            item.state = ItemState.SKIPPED
            item.problem = f"No uploaded image is named “{row.image_filename}”."
        else:
            used.add(key)
            work[item.index] = (row, by_name[key])
        items.append(item)

    named = {row.image_filename.lower() for row in rows}
    for name in images:
        if name.lower() not in named:
            items.append(
                BatchItem(
                    index=len(items),
                    row_number=None,
                    filename=name,
                    brand_name="",
                    state=ItemState.SKIPPED,
                    problem="No spreadsheet row names this image.",
                )
            )
    return items, work


async def run_job(
    job: Job,
    work: dict[int, tuple[ApplicationRow, bytes]],
    extractor: LabelExtractor,
    *,
    concurrency: int,
    max_image_bytes: int,
) -> None:
    limit = asyncio.Semaphore(concurrency)

    async def one(index: int) -> None:
        row, raw = work.pop(index)  # drop the raw upload as soon as it's taken
        item = job.items[index]
        assert row.application is not None
        async with limit:
            try:
                item.check = await check_label(
                    raw, row.application, extractor, max_image_bytes=max_image_bytes
                )
                item.state = ItemState.DONE
            except ImageRejectedError as exc:
                item.state, item.problem = ItemState.FAILED, exc.message
            except ExtractionError as exc:
                item.state, item.problem, item.retryable = (
                    ItemState.FAILED,
                    exc.message,
                    exc.retryable,
                )
                if exc.retryable:
                    job.retry_work[index] = (row, raw)
            except Exception:  # one bad label must never sink the batch
                log.exception("batch item %s failed", index)
                item.state, item.problem = (
                    ItemState.FAILED,
                    "Something went wrong checking this label.",
                )

    job.finished_at = None
    started = time.perf_counter()
    await asyncio.gather(*(one(index) for index in list(work)))
    job.finished_at = time.monotonic()
    log.info(
        "batch %s finished: %d items in %.1fs",
        job.id,
        len(job.items),
        time.perf_counter() - started,
    )


def take_retry_work(job: Job) -> dict[int, tuple[ApplicationRow, bytes]]:
    """Reset the retryable failures to waiting and hand back their work."""
    work, job.retry_work = job.retry_work, {}
    for index in work:
        item = job.items[index]
        item.state, item.problem, item.retryable = ItemState.WAITING, None, False
    return work


class JobStore:
    def __init__(self, *, ttl_seconds: float) -> None:
        self._jobs: dict[str, Job] = {}
        self._ttl = ttl_seconds

    def add(self, items: list[BatchItem]) -> Job:
        self.purge()
        job = Job(id=secrets.token_urlsafe(12), items=items)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        self.purge()
        return self._jobs.get(job_id)

    def purge(self) -> None:
        """Forget jobs that finished more than ``ttl_seconds`` ago (PRD N-4)."""
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and now - job.finished_at > self._ttl
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def cancel_all(self) -> None:
        for job in self._jobs.values():
            if job.task and not job.task.done():
                job.task.cancel()
