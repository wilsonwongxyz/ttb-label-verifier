"""Government health warning rules (V-5 to V-7), per 27 CFR \u00a716.21 and \u00a716.22."""

import re

from app.extract.schema import WarningRead
from app.rules.common import apply_legibility, not_on_label
from app.rules.models import FieldResult, Verdict
from app.rules.normalize import clean, diff_spans, is_blank

REQUIRED_PREFIX = "GOVERNMENT WARNING:"
REQUIRED_WARNING = (
    "GOVERNMENT WARNING: (1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car or operate "
    "machinery, and may cause health problems."
)

_WORD = re.compile(r"\w+")
_PREFIX_AT_START = re.compile(r"\s*(government\s+warning\s*:?)", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return _WORD.findall(text.casefold())


def check_warning_text(read: WarningRead) -> FieldResult:
    """The statement must be word-for-word identical to the regulation (V-5)."""
    field, label = "warning_text", "Health warning wording"
    if is_blank(read.full_text):
        if read.legibility in ("partial", "unreadable"):
            return not_on_label(field, label, REQUIRED_WARNING, read.legibility)
        return FieldResult(
            field=field,
            label=label,
            verdict=Verdict.MISMATCH,
            expected=REQUIRED_WARNING,
            found=None,
            reason="No government health warning found on the label.",
        )
    assert read.full_text is not None
    found = clean(read.full_text)

    required_chunks = REQUIRED_WARNING.split(" ")
    found_chunks = found.split(" ")
    diff = diff_spans(
        required_chunks,
        found_chunks,
        key=[c.casefold() for c in required_chunks],
        found_key=[c.casefold() for c in found_chunks],
        sep=" ",
    )

    def result(verdict: Verdict, reason: str) -> FieldResult:
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected=REQUIRED_WARNING,
                found=found,
                reason=reason,
                diff=None if verdict == Verdict.MATCH else diff,
            ),
            read.legibility,
        )

    if found == REQUIRED_WARNING:
        return result(Verdict.MATCH, "Matches the required wording exactly.")
    if _words(found) != _words(REQUIRED_WARNING):
        return result(
            Verdict.MISMATCH,
            "Wording differs from the required statement. See the highlighted words.",
        )
    if found.casefold() != REQUIRED_WARNING.casefold():
        return result(
            Verdict.NEEDS_REVIEW,
            "Same words, but the punctuation differs. This could be a reading error, "
            "so please check.",
        )
    return result(
        Verdict.MATCH_NOTED,
        "Required wording is present; only capitalization differs.",
    )


def _printed_prefix(read: WarningRead) -> str | None:
    if not is_blank(read.prefix_as_printed):
        assert read.prefix_as_printed is not None
        return clean(read.prefix_as_printed)
    if read.full_text:
        match = _PREFIX_AT_START.match(read.full_text)
        if match:
            return clean(match.group(1))
    return None


def _no_warning(field: str, label: str) -> FieldResult:
    return FieldResult(
        field=field,
        label=label,
        verdict=Verdict.NOT_APPLICABLE,
        expected=REQUIRED_PREFIX,
        found=None,
        reason="No warning to check (see the wording row).",
    )


def check_warning_prefix(read: WarningRead) -> FieldResult:
    """ "GOVERNMENT WARNING:" must be in capital letters (V-6)."""
    field, label = "warning_prefix_caps", "\u201cGOVERNMENT WARNING:\u201d in capitals"
    if is_blank(read.full_text) and is_blank(read.prefix_as_printed):
        return _no_warning(field, label)

    prefix = _printed_prefix(read)

    def result(verdict: Verdict, reason: str) -> FieldResult:
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected=REQUIRED_PREFIX,
                found=prefix,
                reason=reason,
            ),
            read.legibility,
        )

    if prefix is None:
        return result(
            Verdict.MISMATCH, f"The warning must begin with \u201c{REQUIRED_PREFIX}\u201d."
        )
    letters = re.sub(r"[^A-Za-z]", "", prefix)
    if letters == "GOVERNMENTWARNING":
        return result(Verdict.MATCH, "Printed in capital letters.")
    if letters.casefold() == "governmentwarning":
        return result(
            Verdict.MISMATCH,
            f"Printed as \u201c{prefix}\u201d. It must be all capital letters: "
            f"\u201c{REQUIRED_PREFIX}\u201d.",
        )
    return result(Verdict.MISMATCH, f"The warning must begin with \u201c{REQUIRED_PREFIX}\u201d.")


def check_warning_bold(read: WarningRead) -> FieldResult:
    """ "GOVERNMENT WARNING:" must be bold (V-7).

    Font weight can't be measured reliably from a photo, so the best this check can give is
    "looks bold" (a noted match, with the caveat shown). Anything else goes to the agent.
    """
    field, label = "warning_prefix_bold", "\u201cGOVERNMENT WARNING:\u201d in bold"
    if is_blank(read.full_text) and is_blank(read.prefix_as_printed):
        return _no_warning(field, label)

    def result(verdict: Verdict, reason: str) -> FieldResult:
        return apply_legibility(
            FieldResult(
                field=field,
                label=label,
                verdict=verdict,
                expected="Bold",
                found={"yes": "Looks bold", "no": "Looks not bold", "unsure": None}[
                    read.prefix_looks_bold
                ],
                reason=reason,
            ),
            read.legibility,
        )

    if read.prefix_looks_bold == "yes":
        return result(
            Verdict.MATCH_NOTED,
            "Looks bold in the photo. Bold type can't be measured exactly from an image.",
        )
    if read.prefix_looks_bold == "no":
        return result(
            Verdict.NEEDS_REVIEW, "May not be bold. It must be in bold type, so please check."
        )
    return result(Verdict.NEEDS_REVIEW, "Couldn't tell whether it is bold. Please check.")
