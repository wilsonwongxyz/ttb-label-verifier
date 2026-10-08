import pytest

from app.config import Settings
from app.extract.base import ExtractionError
from app.extract.factory import build_extractor
from app.extract.fixture import FixtureExtractor
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import BeverageType
from tests.samples import SAMPLES_DIR, sample_entries


def image(sha256: str) -> PreparedImage:
    return PreparedImage(data=b"", width=900, height=1200, source_sha256=sha256)


async def test_returns_the_recorded_reading_for_each_sample() -> None:
    extractor = FixtureExtractor.from_dir(SAMPLES_DIR)
    for entry in sample_entries():
        reading = await extractor.extract(image(entry["sha256"]), BeverageType.WINE)
        assert reading == LabelExtraction.model_validate(entry["extraction"])


async def test_unknown_image_is_a_clear_error() -> None:
    extractor = FixtureExtractor.from_dir(SAMPLES_DIR)
    with pytest.raises(ExtractionError, match="Demo mode can only read the sample labels"):
        await extractor.extract(image("unknown"), BeverageType.WINE)


def test_factory_picks_the_provider() -> None:
    assert isinstance(build_extractor(Settings(provider="fixture")), FixtureExtractor)
