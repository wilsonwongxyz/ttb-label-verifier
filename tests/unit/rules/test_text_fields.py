import pytest

from app.rules.fields import check_bottler, check_country_of_origin, compare_text
from app.rules.models import Verdict
from app.rules.normalize import normalize
from tests.unit.rules.conftest import application, read


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("STONE'S THROW", "stones throw"),
        ("Stone\u2019s Throw", "stones throw"),
        ("  Old   Tom\nDistillery ", "old tom distillery"),
        ("Jack & Jill", "jack and jill"),
        ("Jack and Jill", "jack and jill"),
        ("Old-Tom", "old tom"),
        ("\uff2f\uff2c\uff24 TOM", "old tom"),  # full-width letters (NFKC)
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize(
    ("expected", "found", "verdict"),
    [
        # Exact text, including surrounding whitespace noise.
        ("OLD TOM DISTILLERY", "OLD TOM DISTILLERY", Verdict.MATCH),
        ("OLD TOM DISTILLERY", " OLD  TOM DISTILLERY\n", Verdict.MATCH),
        # Dave's example: obviously the same brand, so a noted match, not a rejection.
        ("Stone's Throw", "STONE'S THROW", Verdict.MATCH_NOTED),
        ("Stone's Throw", "STONE\u2019S THROW", Verdict.MATCH_NOTED),
        ("Stone's Throw", "Stones Throw", Verdict.MATCH_NOTED),
        ("Jack & Jill", "JACK AND JILL", Verdict.MATCH_NOTED),
        # A near miss is for a person to judge.
        ("OLD TOM DISTILLERY", "OLD TOM DISTILERY", Verdict.NEEDS_REVIEW),
        # Clearly different brands.
        ("OLD TOM DISTILLERY", "NEW TOM DISTILLERY CO", Verdict.MISMATCH),
        ("OLD TOM DISTILLERY", "Blue Ridge Spirits", Verdict.MISMATCH),
    ],
)
def test_compare_text(expected: str, found: str, verdict: Verdict) -> None:
    result = compare_text("brand_name", "Brand name", expected, read(found))
    assert result.verdict == verdict
    assert result.expected == expected
    assert result.found == found


def test_differences_carry_a_character_diff() -> None:
    result = compare_text("brand_name", "Brand name", "OLD TOM", read("OLD TIM"))
    assert result.diff is not None
    assert [(d.op, d.expected, d.found) for d in result.diff if d.op != "equal"] == [
        ("replace", "O", "I")
    ]


def test_exact_match_has_no_diff() -> None:
    assert compare_text("brand_name", "Brand name", "A", read("A")).diff is None


def test_missing_on_label_is_a_mismatch() -> None:
    result = compare_text("brand_name", "Brand name", "OLD TOM", read(None))
    assert result.verdict == Verdict.MISMATCH
    assert result.reason == "No brand name found on the label."


@pytest.mark.parametrize("legibility", ["partial", "unreadable"])
def test_unreadable_field_needs_review(legibility: str) -> None:
    result = compare_text("brand_name", "Brand name", "OLD TOM", read(None, legibility))  # type: ignore[arg-type]
    assert result.verdict == Verdict.NEEDS_REVIEW


@pytest.mark.parametrize("found", ["OLD TOM", "NOTHING ALIKE AT ALL"])
def test_partially_legible_text_is_never_a_confident_verdict(found: str) -> None:
    result = compare_text("brand_name", "Brand name", "OLD TOM", read(found, "partial"))
    assert result.verdict == Verdict.NEEDS_REVIEW
    assert result.reason.startswith("Hard to read on the label")


def test_blank_application_value_needs_review() -> None:
    result = compare_text("brand_name", "Brand name", "  ", read("OLD TOM"))
    assert result.verdict == Verdict.NEEDS_REVIEW


@pytest.mark.parametrize(
    ("found", "verdict"),
    [
        ("Bottled by Old Tom Distillery, Bardstown, Kentucky", Verdict.MATCH),
        ("BOTTLED BY OLD TOM DISTILLERY, BARDSTOWN, KENTUCKY", Verdict.MATCH_NOTED),
        # Addresses are formatted many ways: never an automatic rejection.
        ("Bottled by Old Tom Distillery, Bardstown, KY", Verdict.NEEDS_REVIEW),
        ("Produced by Someone Else Inc., Portland, OR", Verdict.NEEDS_REVIEW),
        (None, Verdict.MISMATCH),
    ],
)
def test_bottler_is_lenient(found: str | None, verdict: Verdict) -> None:
    assert check_bottler(application(), read(found)).verdict == verdict


def test_country_of_origin_only_applies_to_imports() -> None:
    result = check_country_of_origin(application(imported=False), read(None))
    assert result.verdict == Verdict.NOT_APPLICABLE


@pytest.mark.parametrize(
    ("found", "verdict"),
    [
        ("Product of Scotland", Verdict.NEEDS_REVIEW),
        ("Scotland", Verdict.MATCH),
        (None, Verdict.MISMATCH),
    ],
)
def test_country_of_origin_for_imports(found: str | None, verdict: Verdict) -> None:
    app = application(imported=True, country_of_origin="Scotland")
    assert check_country_of_origin(app, read(found)).verdict == verdict
