from typing import Protocol

from app.extract.schema import LabelExtraction
from app.imaging.prepare import PreparedImage
from app.rules.models import BeverageType


class ExtractionError(Exception):
    """The label couldn't be read this time. ``message`` is safe to show to the user."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class LabelExtractor(Protocol):
    """Reads a label image into a LabelExtraction. The only place a model is called."""

    async def extract(
        self, image: PreparedImage, beverage_type: BeverageType
    ) -> LabelExtraction: ...
