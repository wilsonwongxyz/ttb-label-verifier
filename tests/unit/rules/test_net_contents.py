from decimal import Decimal

import pytest

from app.rules.fields import check_net_contents, parse_quantity
from app.rules.models import Verdict
from tests.unit.rules.conftest import application, read


@pytest.mark.parametrize(
    ("text", "value", "unit"),
    [
        ("750 mL", "750", "ml"),
        ("750ML", "750", "ml"),
        ("750 milliliters", "750", "ml"),
        ("75 cL", "75", "cl"),
        ("1.75 L", "1.75", "l"),
        ("1 Liter", "1", "l"),
        ("1 litre", "1", "l"),
        ("1,75 l", "1.75", "l"),
        ("1,750 mL", "1750", "ml"),
        ("12 FL. OZ.", "12", "fl oz"),
        ("12 fl oz", "12", "fl oz"),
        ("16 fluid ounces", "16", "fl oz"),
        ("12 oz", "12", "fl oz"),
        ("750 mL (25.4 FL OZ)", "750", "ml"),
    ],
)
def test_parse_quantity(text: str, value: str, unit: str) -> None:
    parsed = parse_quantity(text)
    assert parsed is not None
    assert (parsed.value, parsed.unit) == (Decimal(value), unit)


@pytest.mark.parametrize("text", ["", "one bottle", "750", "lots"])
def test_parse_quantity_rejects_non_volumes(text: str) -> None:
    assert parse_quantity(text) is None


@pytest.mark.parametrize(
    ("expected", "found", "verdict"),
    [
        ("750 mL", "750 mL", Verdict.MATCH),
        ("750 mL", "750ML", Verdict.MATCH),
        # Same amount, different units.
        ("750 mL", "75 cL", Verdict.MATCH_NOTED),
        ("1.75 L", "1750 mL", Verdict.MATCH_NOTED),
        ("25.4 fl oz", "750 mL", Verdict.MATCH_NOTED),  # within rounding tolerance
        # Different amounts.
        ("750 mL", "700 mL", Verdict.MISMATCH),
        ("750 mL", "1 L", Verdict.MISMATCH),
        ("12 fl oz", "355 mL", Verdict.MATCH_NOTED),
        ("12 fl oz", "16 fl oz", Verdict.MISMATCH),
        # Unparseable.
        ("750 mL", "one fifth", Verdict.NEEDS_REVIEW),
    ],
)
def test_check_net_contents(expected: str, found: str, verdict: Verdict) -> None:
    result = check_net_contents(application(net_contents=expected), read(found))
    assert result.verdict == verdict


def test_unit_conversion_is_explained() -> None:
    result = check_net_contents(application(net_contents="750 mL"), read("75 cL"))
    assert result.reason == "Same amount in different units (750 mL = 75 cL)."


def test_missing_on_label_is_a_mismatch() -> None:
    assert check_net_contents(application(), read(None)).verdict == Verdict.MISMATCH
