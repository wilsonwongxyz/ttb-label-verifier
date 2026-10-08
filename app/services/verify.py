"""Prepare → extract → compare, for one label."""

import asyncio
import time
from dataclasses import dataclass

from app.extract.base import LabelExtractor
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage, prepare_image
from app.rules import verify
from app.rules.models import ApplicationData, VerificationReport


@dataclass(frozen=True)
class LabelCheck:
    report: VerificationReport
    extraction: LabelExtraction
    image: PreparedImage
    timings_ms: dict[str, int]


async def check_label(
    raw_image: bytes,
    application: ApplicationData,
    extractor: LabelExtractor,
    *,
    max_image_bytes: int,
) -> LabelCheck:
    """Raises ImageRejectedError or ExtractionError with a user-facing message."""
    t0 = time.perf_counter()
    image = await asyncio.to_thread(prepare_image, raw_image, max_bytes=max_image_bytes)
    t1 = time.perf_counter()
    extraction = await extractor.extract(image, application.beverage_type)
    t2 = time.perf_counter()
    report = verify(application, extraction)
    t3 = time.perf_counter()
    return LabelCheck(
        report=report,
        extraction=extraction,
        image=image,
        timings_ms={
            "prepare": round((t1 - t0) * 1000),
            "extract": round((t2 - t1) * 1000),
            "rules": round((t3 - t2) * 1000),
        },
    )
