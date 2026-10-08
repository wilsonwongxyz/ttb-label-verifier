"""Helpers shared by every field rule."""

from app.extract.schema import Legibility
from app.rules.models import FieldResult, Verdict

_HARD_TO_READ: frozenset[Legibility] = frozenset({"partial", "unreadable"})
_CONFIDENT = frozenset({Verdict.MATCH, Verdict.MATCH_NOTED, Verdict.MISMATCH})


def apply_legibility(result: FieldResult, legibility: Legibility) -> FieldResult:
    """A field the model could only partly read is never a confident verdict either way.

    A false "Match" is the worst error this tool can make (PRD §8), and a "Mismatch" built
    on a misread is noise for the agent, so both become "Needs Review".
    """
    if legibility in _HARD_TO_READ and result.verdict in _CONFIDENT:
        return result.model_copy(
            update={
                "verdict": Verdict.NEEDS_REVIEW,
                "reason": f"Hard to read on the label, so please check by eye. {result.reason}",
            }
        )
    return result


def not_on_label(
    field: str, label: str, expected: str | None, legibility: Legibility
) -> FieldResult:
    """Result for a required field the model returned no text for."""
    if legibility in _HARD_TO_READ:
        return FieldResult(
            field=field,
            label=label,
            verdict=Verdict.NEEDS_REVIEW,
            expected=expected,
            found=None,
            reason=f"Couldn't read the {label.lower()} on the label. Please check by eye.",
        )
    return FieldResult(
        field=field,
        label=label,
        verdict=Verdict.MISMATCH,
        expected=expected,
        found=None,
        reason=f"No {label.lower()} found on the label.",
    )
