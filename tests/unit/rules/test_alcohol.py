from decimal import Decimal

import pytest

from app.rules.fields import check_alcohol, parse_alcohol
from app.rules.models import BeverageType, Verdict
from tests.unit.rules.conftest import application, read


@pytest.mark.parametrize(
    ("text", "abv", "proof"),
    [
        ("45% Alc./Vol. (90 Proof)", "45", "90"),
        ("Alc. 45% by Vol.", "45", None),
        ("ALC 12.5% BY VOL", "12.5", None),
        ("13,5 % vol", "13.5", None),
        ("40 % ABV", "40", None),
        ("80 proof", None, "80"),
        ("86.8° Proof / 43.4% Alc/Vol", "43.4", "86.8"),
        ("strong stuff", None, None),
    ],
)
def test_parse_alcohol(text: str, abv: str | None, proof: str | None) -> None:
    parsed = parse_alcohol(text)
    assert parsed.abv == (Decimal(abv) if abv else None)
    assert parsed.proof == (Decimal(proof) if proof else None)


@pytest.mark.parametrize(
    ("expected", "found", "verdict"),
    [
        # The README's sample label.
        ("45% Alc./Vol. (90 Proof)", "45% Alc./Vol. (90 Proof)", Verdict.MATCH),
        # Same number, different wording.
        ("45% Alc./Vol. (90 Proof)", "Alc. 45% by Vol.", Verdict.MATCH_NOTED),
        ("45% Alc./Vol.", "45.0% ALC/VOL", Verdict.MATCH_NOTED),
        # Wrong number on the label.
        ("45% Alc./Vol. (90 Proof)", "40% Alc./Vol. (80 Proof)", Verdict.MISMATCH),
        ("45% Alc./Vol.", "46% Alc./Vol.", Verdict.MISMATCH),
        # Proof printed on the label must be twice the ABV.
        ("45% Alc./Vol.", "45% Alc./Vol. (95 Proof)", Verdict.MISMATCH),
        # Proof on the label disagrees with the (inconsistent) application.
        ("45% Alc./Vol. (92 Proof)", "45% Alc./Vol. (90 Proof)", Verdict.MISMATCH),
        # Can't parse a percentage: a person compares.
        ("45% Alc./Vol.", "Ninety proof", Verdict.NEEDS_REVIEW),
    ],
)
def test_check_alcohol(expected: str, found: str, verdict: Verdict) -> None:
    result = check_alcohol(application(alcohol_content=expected), read(found))
    assert result.verdict == verdict


def test_mismatch_reason_names_both_values() -> None:
    result = check_alcohol(application(alcohol_content="45% Alc./Vol."), read("40% Alc./Vol."))
    assert result.reason == "Label says 40% but the application says 45%."


def test_proof_reason_explains_the_arithmetic() -> None:
    result = check_alcohol(application(alcohol_content="45%"), read("45% (95 Proof)"))
    assert result.reason == "Label shows 95 proof, but 45% ABV is 90 proof."


def test_missing_on_spirits_label_is_a_mismatch() -> None:
    result = check_alcohol(application(), read(None))
    assert result.verdict == Verdict.MISMATCH


@pytest.mark.parametrize("beverage", [BeverageType.WINE, BeverageType.MALT_BEVERAGE])
def test_optional_for_wine_and_beer_when_not_declared(beverage: BeverageType) -> None:
    app = application(beverage_type=beverage, alcohol_content=None)
    assert check_alcohol(app, read(None)).verdict == Verdict.NOT_APPLICABLE


def test_declared_on_wine_application_but_missing_from_label() -> None:
    app = application(beverage_type=BeverageType.WINE, alcohol_content="12.5% Alc./Vol.")
    assert check_alcohol(app, read(None)).verdict == Verdict.MISMATCH


def test_on_label_but_not_in_application_needs_review() -> None:
    app = application(beverage_type=BeverageType.WINE, alcohol_content=None)
    assert check_alcohol(app, read("12.5% Alc./Vol.")).verdict == Verdict.NEEDS_REVIEW


def test_partially_legible_mismatch_needs_review() -> None:
    result = check_alcohol(application(), read("40% Alc./Vol.", "partial"))
    assert result.verdict == Verdict.NEEDS_REVIEW
