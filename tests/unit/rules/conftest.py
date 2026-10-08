from typing import Any

import pytest

from app.extract.schema import LabelExtraction, Legibility, ReadValue, WarningRead
from app.rules.models import ApplicationData, BeverageType
from app.rules.warning import REQUIRED_WARNING


def read(text: str | None, legibility: Legibility | None = None) -> ReadValue:
    if legibility is None:
        legibility = "absent" if text is None else "clear"
    return ReadValue(text=text, legibility=legibility)


def warning(
    text: str | None = REQUIRED_WARNING,
    *,
    prefix: str | None = None,
    bold: str = "yes",
    legibility: Legibility | None = None,
) -> WarningRead:
    if legibility is None:
        legibility = "absent" if text is None else "clear"
    return WarningRead.model_validate(
        {
            "full_text": text,
            "prefix_as_printed": prefix,
            "prefix_looks_bold": bold,
            "legibility": legibility,
        }
    )


def application(**overrides: Any) -> ApplicationData:
    """The README's sample label (OLD TOM DISTILLERY) as an application."""
    values: dict[str, Any] = {
        "beverage_type": BeverageType.DISTILLED_SPIRITS,
        "brand_name": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol_content": "45% Alc./Vol. (90 Proof)",
        "net_contents": "750 mL",
        "bottler_name_address": "Bottled by Old Tom Distillery, Bardstown, Kentucky",
        "imported": False,
        "country_of_origin": None,
    }
    values.update(overrides)
    return ApplicationData(**values)


def extraction(**overrides: Any) -> LabelExtraction:
    """A clean, fully legible read of the sample label."""
    values: dict[str, Any] = {
        "brand_name": read("OLD TOM DISTILLERY"),
        "class_type": read("Kentucky Straight Bourbon Whiskey"),
        "alcohol_content": read("45% Alc./Vol. (90 Proof)"),
        "net_contents": read("750 mL"),
        "bottler_name_address": read("Bottled by Old Tom Distillery, Bardstown, Kentucky"),
        "country_of_origin": read(None),
        "government_warning": warning(),
    }
    values.update(overrides)
    return LabelExtraction(**values)


@pytest.fixture
def sample_app() -> ApplicationData:
    return application()


@pytest.fixture
def sample_extraction() -> LabelExtraction:
    return extraction()
