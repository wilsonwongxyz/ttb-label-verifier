import asyncio

from app.batch.csv_io import ApplicationRow
from app.batch.jobs import ItemState, JobStore, build_items, run_job, take_retry_work
from app.extract.base import ExtractionError
from app.extract.fixture import FixtureExtractor
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import ApplicationData, BeverageType, OverallStatus
from tests.samples import SAMPLES_DIR, sample, sample_bytes

LIMIT = 10 * 1024 * 1024


def row(n: int, filename: str, name: str = "old_tom_bourbon") -> ApplicationRow:
    return ApplicationRow(n, filename, ApplicationData.model_validate(sample(name)["application"]))


def test_build_items_pairs_rows_with_images() -> None:
    rows = [
        row(2, "A.png"),
        row(3, "missing.png"),
        ApplicationRow(4, "b.png", None, "Enter the brand name."),
        row(5, "a.png"),
    ]
    items, work = build_items(rows, {"a.png": b"1", "b.png": b"2", "extra.png": b"3"})

    assert [(i.filename, i.state) for i in items] == [
        ("A.png", ItemState.WAITING),
        ("missing.png", ItemState.SKIPPED),
        ("b.png", ItemState.SKIPPED),
        ("a.png", ItemState.SKIPPED),
        ("extra.png", ItemState.SKIPPED),  # b.png is named by row 4, so not listed again
    ]
    assert list(work) == [0]
    assert items[1].problem == "No uploaded image is named “missing.png”."
    assert items[2].problem == "Enter the brand name."
    assert items[3].problem == "Another row already uses this image."
    assert items[4].problem == "No spreadsheet row names this image."


async def test_run_job_checks_every_label() -> None:
    names = ["old_tom_bourbon", "copper_ridge_vodka_wrong_abv", "harbor_light_rum_title_case"]
    rows = [row(n + 2, f"{name}.png", name) for n, name in enumerate(names)]
    items, work = build_items(rows, {f"{n}.png": sample_bytes(n) for n in names})
    job = JobStore(ttl_seconds=60).add(items)

    await run_job(
        job, work, FixtureExtractor.from_dir(SAMPLES_DIR), concurrency=2, max_image_bytes=LIMIT
    )

    assert job.finished and job.done_count == 3
    assert [i.status for i in job.items] == [
        OverallStatus.ALL_CLEAR,
        OverallStatus.ISSUES_FOUND,
        OverallStatus.ISSUES_FOUND,
    ]
    assert work == {}  # raw uploads are released


class FlakyExtractor:
    """Fails each image the first time, succeeds after; tracks peak concurrency."""

    def __init__(self) -> None:
        self.seen: set[str] = set()
        self.active = 0
        self.peak = 0

    async def extract(self, image: PreparedImage, beverage_type: BeverageType) -> LabelExtraction:
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        if image.source_sha256 not in self.seen:
            self.seen.add(image.source_sha256)
            raise ExtractionError("Try again.", retryable=True)
        return LabelExtraction.model_validate(sample("old_tom_bourbon")["extraction"])


async def test_failures_are_isolated_and_retryable() -> None:
    names = ["old_tom_bourbon", "stones_throw_gin", "copper_ridge_vodka_wrong_abv"]
    rows = [row(n + 2, f"{name}.png") for n, name in enumerate(names)]
    images = {f"{n}.png": sample_bytes(n) for n in names}
    images["broken.png"] = b"not an image"
    rows.append(row(9, "broken.png"))
    items, work = build_items(rows, images)
    job = JobStore(ttl_seconds=60).add(items)
    extractor = FlakyExtractor()

    await run_job(job, work, extractor, concurrency=2, max_image_bytes=LIMIT)
    assert extractor.peak <= 2
    assert [i.state for i in job.items] == [ItemState.FAILED] * 4
    assert job.items[3].problem is not None and "isn't a photo" in job.items[3].problem
    assert sorted(job.retry_work) == [0, 1, 2]  # the broken image isn't retryable

    await run_job(job, take_retry_work(job), extractor, concurrency=2, max_image_bytes=LIMIT)
    assert [i.state for i in job.items] == [ItemState.DONE] * 3 + [ItemState.FAILED]
    assert job.retry_work == {}


def test_store_forgets_finished_jobs_after_ttl() -> None:
    store = JobStore(ttl_seconds=0)
    running = store.add([])
    finished = store.add([])
    finished.finished_at = 0.0
    store.purge()
    assert store.get(running.id) is running
    assert store.get(finished.id) is None
