import pytest

from app.rules.models import Verdict
from app.rules.warning import (
    REQUIRED_WARNING,
    check_warning_bold,
    check_warning_prefix,
    check_warning_text,
)
from tests.unit.rules.conftest import warning

BODY = REQUIRED_WARNING.removeprefix("GOVERNMENT WARNING: ")


# --- Wording (V-5) ----------------------------------------------------------------------


def test_exact_warning_matches() -> None:
    result = check_warning_text(warning())
    assert result.verdict == Verdict.MATCH
    assert result.diff is None


def test_line_breaks_and_spacing_are_ignored() -> None:
    wrapped = REQUIRED_WARNING.replace(" (2) ", "\n(2)  ").replace("Surgeon ", "Surgeon\n")
    assert check_warning_text(warning(wrapped)).verdict == Verdict.MATCH


@pytest.mark.parametrize(
    ("text", "changed"),
    [
        # Reworded.
        (REQUIRED_WARNING.replace("should not drink", "shouldn't drink"), "should not"),
        (REQUIRED_WARNING.replace("Surgeon General", "Surgeon-General's office"), "General,"),
        # Softened.
        (REQUIRED_WARNING.replace("women should", "women may wish to"), "should"),
        # Truncated: second clause dropped.
        (REQUIRED_WARNING.split(" (2)")[0], "(2)"),
        # Words added.
        (REQUIRED_WARNING + " Please drink responsibly.", ""),
    ],
)
def test_any_wording_change_is_a_mismatch(text: str, changed: str) -> None:
    result = check_warning_text(warning(text))
    assert result.verdict == Verdict.MISMATCH
    assert result.diff is not None
    assert any(span.op != "equal" for span in result.diff)
    if changed:
        assert any(changed in span.expected for span in result.diff if span.op != "equal")


def test_diff_spans_rebuild_both_texts() -> None:
    text = REQUIRED_WARNING.replace("should not drink", "should avoid drinking")
    diff = check_warning_text(warning(text)).diff
    assert diff is not None
    assert "".join(span.expected for span in diff) == REQUIRED_WARNING
    assert "".join(span.found for span in diff) == text
    changed = [(s.expected, s.found) for s in diff if s.op != "equal"]
    assert changed == [("not drink ", "avoid drinking ")]


def test_lead_in_reported_separately_is_put_back() -> None:
    # Seen with real model output: the lead-in only in prefix_as_printed.
    read = warning(BODY, prefix="GOVERNMENT WARNING:")
    assert check_warning_text(read).verdict == Verdict.MATCH
    assert check_warning_prefix(read).verdict == Verdict.MATCH


def test_missing_lead_in_is_still_caught() -> None:
    # No lead-in on the label: nothing to put back, so the wording check fails.
    assert check_warning_text(warning(BODY, prefix=None)).verdict == Verdict.MISMATCH


def test_title_case_lead_in_reported_separately_still_fails_capitals() -> None:
    read = warning(BODY, prefix="Government Warning:")
    assert check_warning_text(read).verdict == Verdict.MATCH_NOTED
    assert check_warning_prefix(read).verdict == Verdict.MISMATCH


def test_missing_warning_is_a_mismatch() -> None:
    result = check_warning_text(warning(None))
    assert result.verdict == Verdict.MISMATCH
    assert result.reason == "No government health warning found on the label."


def test_unreadable_warning_needs_review() -> None:
    assert check_warning_text(warning(None, legibility="unreadable")).verdict == (
        Verdict.NEEDS_REVIEW
    )


def test_punctuation_only_difference_needs_review() -> None:
    text = REQUIRED_WARNING.replace("pregnancy because", "pregnancy, because")
    assert check_warning_text(warning(text)).verdict == Verdict.NEEDS_REVIEW


def test_title_case_prefix_is_flagged_by_the_prefix_rule_not_the_wording_rule() -> None:
    text = "Government Warning: " + BODY
    assert check_warning_text(warning(text)).verdict == Verdict.MATCH_NOTED
    assert check_warning_prefix(warning(text)).verdict == Verdict.MISMATCH


def test_partially_legible_exact_warning_needs_review() -> None:
    assert check_warning_text(warning(legibility="partial")).verdict == Verdict.NEEDS_REVIEW


# --- Capitals (V-6) ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "prefix", "verdict"),
    [
        (REQUIRED_WARNING, None, Verdict.MATCH),
        (REQUIRED_WARNING, "GOVERNMENT WARNING:", Verdict.MATCH),
        # Jenny's rejected label: title case.
        ("Government Warning: " + BODY, None, Verdict.MISMATCH),
        ("Government Warning: " + BODY, "Government Warning:", Verdict.MISMATCH),
        ("government warning: " + BODY, None, Verdict.MISMATCH),
        ("GOVERNMENT Warning: " + BODY, None, Verdict.MISMATCH),
        # Prefix missing entirely.
        (BODY, None, Verdict.MISMATCH),
        ("WARNING: " + BODY, None, Verdict.MISMATCH),
    ],
)
def test_prefix_must_be_capitals(text: str, prefix: str | None, verdict: Verdict) -> None:
    assert check_warning_prefix(warning(text, prefix=prefix)).verdict == verdict


def test_title_case_reason_shows_what_was_printed() -> None:
    result = check_warning_prefix(warning("Government Warning: " + BODY))
    assert result.found == "Government Warning:"
    assert "must be all capital letters" in result.reason


def test_prefix_not_applicable_without_a_warning() -> None:
    assert check_warning_prefix(warning(None)).verdict == Verdict.NOT_APPLICABLE


# --- Bold (V-7) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bold", "verdict"),
    [
        ("yes", Verdict.MATCH_NOTED),  # never a plain MATCH: weight can't be measured
        ("no", Verdict.NEEDS_REVIEW),
        ("unsure", Verdict.NEEDS_REVIEW),
    ],
)
def test_bold(bold: str, verdict: Verdict) -> None:
    assert check_warning_bold(warning(bold=bold)).verdict == verdict


def test_bold_not_applicable_without_a_warning() -> None:
    assert check_warning_bold(warning(None)).verdict == Verdict.NOT_APPLICABLE


def test_bold_on_a_hard_to_read_warning_needs_review() -> None:
    result = check_warning_bold(warning(bold="yes", legibility="partial"))
    assert result.verdict == Verdict.NEEDS_REVIEW
