"""Rules for the application fields: brand, class/type, alcohol, net contents, bottler, origin.

Each rule compares what the applicant declared with what the model read off the label and
returns one FieldResult. Rules never call the model and never raise on odd input; anything
they can't interpret becomes "Needs Review".
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from rapidfuzz import fuzz

from app.extract.schema import ReadValue
from app.rules.common import apply_legibility, not_on_label
from app.rules.models import ApplicationData, BeverageType, FieldResult, Verdict
from app.rules.normalize import clean, diff_spans, is_blank, normalize

# Normalized texts at least this similar (0-100) are flagged for review rather than rejected.
FUZZY_REVIEW_THRESHOLD = 90.0
# Allowed rounding error when the label and the application use different volume units.
NET_CONTENTS_TOLERANCE = Decimal("0.005")


def compare_text(
    field: str,
    label: str,
    expected: str | None,
    read: ReadValue,
    *,
    lenient: bool = False,
) -> FieldResult:
    """Compare free text such as a brand name.

    With ``lenient`` (used for addresses), any difference is sent for review instead of
    being a mismatch, because addresses are legitimately formatted many ways.
    """
    if is_blank(read.text):
        return not_on_label(field, label, expected, read.legibility)
    assert read.text is not None
    found = read.text

    def result(verdict: Verdict, reason: str, *, with_diff: bool = False) -> FieldResult:
        diff = None
        if with_diff and expected is not None:
            diff = diff_spans(list(clean(expected)), list(clean(found)))
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected=expected,
                found=found,
                reason=reason,
                diff=diff,
            ),
            read.legibility,
        )

    if is_blank(expected):
        return result(Verdict.NEEDS_REVIEW, "The application has no value to compare against.")
    assert expected is not None

    if clean(expected) == clean(found):
        return result(Verdict.MATCH, "Matches the application.")
    if normalize(expected) == normalize(found):
        return result(
            Verdict.MATCH_NOTED,
            "Same wording; only capitalization or punctuation differs.",
            with_diff=True,
        )
    if lenient:
        return result(
            Verdict.NEEDS_REVIEW,
            "Differs from the application. Formatting often varies here, so please check.",
            with_diff=True,
        )
    if fuzz.ratio(normalize(expected), normalize(found)) >= FUZZY_REVIEW_THRESHOLD:
        return result(
            Verdict.NEEDS_REVIEW,
            "Very similar but not identical. Please check the highlighted differences.",
            with_diff=True,
        )
    return result(Verdict.MISMATCH, "Doesn't match the application.", with_diff=True)


# --- Alcohol content (V-3) --------------------------------------------------------------

_NUMBER = r"(\d+(?:[.,]\d+)?)"
_ABV = re.compile(_NUMBER + r"\s*%")
_PROOF = re.compile(_NUMBER + r"\s*°?\s*proof\b", re.IGNORECASE)


@dataclass(frozen=True)
class AlcoholContent:
    abv: Decimal | None
    proof: Decimal | None


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def parse_alcohol(text: str) -> AlcoholContent:
    """Pull ABV and proof out of statements like "45% Alc./Vol. (90 Proof)"."""
    abv = _ABV.search(text)
    proof = _PROOF.search(text)
    return AlcoholContent(
        abv=_decimal(abv.group(1)) if abv else None,
        proof=_decimal(proof.group(1)) if proof else None,
    )


def _fmt(value: Decimal) -> str:
    return f"{value.normalize():f}"


def check_alcohol(app: ApplicationData, read: ReadValue) -> FieldResult:
    field, label = "alcohol_content", "Alcohol content"
    expected = app.alcohol_content
    optional = app.beverage_type in (BeverageType.WINE, BeverageType.MALT_BEVERAGE)

    if is_blank(read.text):
        if read.legibility == "absent" and optional and is_blank(expected):
            return FieldResult(
                field=field,
                label=label,
                verdict=Verdict.NOT_APPLICABLE,
                expected=expected,
                found=None,
                reason="Not stated, and not always required for this beverage type.",
            )
        return not_on_label(field, label, expected, read.legibility)
    assert read.text is not None
    found = read.text

    def result(verdict: Verdict, reason: str) -> FieldResult:
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected=expected,
                found=found,
                reason=reason,
            ),
            read.legibility,
        )

    if is_blank(expected):
        return result(
            Verdict.NEEDS_REVIEW, "The application has no alcohol content to compare against."
        )
    assert expected is not None

    want, got = parse_alcohol(expected), parse_alcohol(found)
    if want.abv is None or got.abv is None:
        return result(
            Verdict.NEEDS_REVIEW, "Couldn't interpret the alcohol content. Please compare by eye."
        )
    if want.abv != got.abv:
        return result(
            Verdict.MISMATCH,
            f"Label says {_fmt(got.abv)}% but the application says {_fmt(want.abv)}%.",
        )
    if got.proof is not None and got.proof != 2 * got.abv:
        return result(
            Verdict.MISMATCH,
            f"Label shows {_fmt(got.proof)} proof, but {_fmt(got.abv)}% ABV is "
            f"{_fmt(2 * got.abv)} proof.",
        )
    if want.proof is not None and got.proof is not None and want.proof != got.proof:
        return result(
            Verdict.MISMATCH,
            f"Label shows {_fmt(got.proof)} proof but the application says "
            f"{_fmt(want.proof)} proof.",
        )
    if clean(expected) == clean(found):
        return result(Verdict.MATCH, "Matches the application.")
    return result(Verdict.MATCH_NOTED, "Same alcohol content, written differently.")


# --- Net contents (V-4) -----------------------------------------------------------------

_ML_PER_UNIT = {
    "ml": Decimal(1),
    "cl": Decimal(10),
    "l": Decimal(1000),
    "fl oz": Decimal("29.5735"),
}
_UNIT_ALIASES = {
    "ml": "ml",
    "milliliter": "ml",
    "millilitre": "ml",
    "cl": "cl",
    "centiliter": "cl",
    "centilitre": "cl",
    "l": "l",
    "liter": "l",
    "litre": "l",
    "fl oz": "fl oz",
    "fluid ounce": "fl oz",
    "oz": "fl oz",
}
_QUANTITY = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*"
    r"(ml|millilit(?:er|re)s?|cl|centilit(?:er|re)s?|lit(?:er|re)s?|l"
    r"|fl\.?\s*oz\.?|fluid\s+ounces?|oz\.?)(?![a-z])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str

    @property
    def ml(self) -> Decimal:
        return self.value * _ML_PER_UNIT[self.unit]

    def __str__(self) -> str:
        unit = {"ml": "mL", "cl": "cL", "l": "L"}.get(self.unit, self.unit)
        return f"{_fmt(self.value)} {unit}"


def _parse_number(text: str) -> Decimal | None:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):  # 1,750 or 1,750.5
        text = text.replace(",", "")
    return _decimal(text)


def _canonical_unit(raw: str) -> str:
    unit = re.sub(r"[.\s]+", " ", raw.lower()).strip()
    unit = re.sub(r"^fl ?oz$", "fl oz", unit)
    unit = re.sub(r"s$", "", unit) if unit not in ("ml", "cl") else unit
    return _UNIT_ALIASES[unit]


def parse_quantity(text: str) -> Quantity | None:
    """Parse the first volume in a statement such as "750 mL (25.4 FL OZ)"."""
    match = _QUANTITY.search(text)
    if not match:
        return None
    value = _parse_number(match.group(1))
    if value is None:
        return None
    return Quantity(value=value, unit=_canonical_unit(match.group(2)))


def check_net_contents(app: ApplicationData, read: ReadValue) -> FieldResult:
    field, label = "net_contents", "Net contents"
    expected = app.net_contents

    if is_blank(read.text):
        return not_on_label(field, label, expected, read.legibility)
    assert read.text is not None
    found = read.text

    def result(verdict: Verdict, reason: str) -> FieldResult:
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected=expected,
                found=found,
                reason=reason,
            ),
            read.legibility,
        )

    if is_blank(expected):
        return result(Verdict.NEEDS_REVIEW, "The application has no value to compare against.")

    want, got = parse_quantity(expected), parse_quantity(found)
    if want is None or got is None:
        return result(
            Verdict.NEEDS_REVIEW, "Couldn't interpret the net contents. Please compare by eye."
        )
    if want.unit == got.unit:
        if want.value == got.value:
            return result(Verdict.MATCH, "Matches the application.")
        return result(Verdict.MISMATCH, f"Label says {got} but the application says {want}.")
    if abs(want.ml - got.ml) <= want.ml * NET_CONTENTS_TOLERANCE:
        return result(Verdict.MATCH_NOTED, f"Same amount in different units ({want} = {got}).")
    return result(Verdict.MISMATCH, f"Label says {got} but the application says {want}.")


# --- Bottler and origin (V-8) -----------------------------------------------------------


def check_bottler(app: ApplicationData, read: ReadValue) -> FieldResult:
    return compare_text(
        "bottler_name_address",
        "Bottler name and address",
        app.bottler_name_address,
        read,
        lenient=True,
    )


def check_country_of_origin(app: ApplicationData, read: ReadValue) -> FieldResult:
    if not app.imported:
        return FieldResult(
            field="country_of_origin",
            label="Country of origin",
            verdict=Verdict.NOT_APPLICABLE,
            expected=app.country_of_origin,
            found=read.text,
            reason="Only required for imported products.",
        )
    return compare_text(
        "country_of_origin", "Country of origin", app.country_of_origin, read, lenient=True
    )
