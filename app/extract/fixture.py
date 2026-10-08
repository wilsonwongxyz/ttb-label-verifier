import json
from pathlib import Path

from app.extract.base import ExtractionError
from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import BeverageType


class FixtureExtractor:
    """Offline extractor: returns recorded readings for known sample images.

    Used by tests and by the keyless demo (``LV_PROVIDER=fixture``). Images are recognized by
    the SHA-256 of the uploaded file, listed in ``fixtures.json`` next to the samples.
    """

    def __init__(self, readings: dict[str, LabelExtraction]) -> None:
        self._readings = readings

    @classmethod
    def from_dir(cls, directory: Path) -> "FixtureExtractor":
        index = json.loads((directory / "fixtures.json").read_text())
        return cls(
            {
                entry["sha256"]: LabelExtraction.model_validate(entry["extraction"])
                for entry in index["samples"]
            }
        )

    async def extract(self, image: PreparedImage, beverage_type: BeverageType) -> LabelExtraction:
        try:
            return self._readings[image.source_sha256]
        except KeyError:
            raise ExtractionError(
                "Demo mode can only read the sample labels. Please use one of the samples.",
                retryable=False,
            ) from None
