"""Scoring one evaluation case, and summarizing a run. Pure functions, unit-tested."""

import statistics
from dataclasses import dataclass, field

from app.extract.schema import LabelExtraction
from app.rules import verify
from app.rules.models import ApplicationData, OverallStatus, VerificationReport

READ_FIELDS = [
    "brand_name",
    "class_type",
    "alcohol_content",
    "net_contents",
    "bottler_name_address",
    "country_of_origin",
]

# On a degraded photo, a careful "please look" is an acceptable answer; a false pass is not.
_CAUTIOUS = {OverallStatus.NEEDS_REVIEW.value, OverallStatus.CANT_READ.value}


@dataclass
class CaseResult:
    case: str
    photo: str
    expected_status: str
    got_status: str | None  # None when the extraction failed outright
    seconds: float
    fields_right: int = 0
    fields_total: int = 0
    text_exact: int = 0
    text_total: int = 0
    error: str | None = None
    wrong_fields: list[str] = field(default_factory=list)

    @property
    def exact(self) -> bool:
        return self.got_status == self.expected_status

    @property
    def acceptable(self) -> bool:
        """Right, or cautious about a degraded photo (never a false pass)."""
        if self.exact:
            return True
        return self.photo != "clean" and self.got_status in _CAUTIOUS

    @property
    def false_clear(self) -> bool:
        """The critical failure: "All clear" on a label that has a real problem (PRD §8)."""
        return (
            self.got_status == OverallStatus.ALL_CLEAR.value
            and self.expected_status != OverallStatus.ALL_CLEAR.value
        )


def grade(
    case: dict[str, object],
    reading: LabelExtraction | None,
    seconds: float,
    error: str | None = None,
) -> CaseResult:
    application = ApplicationData.model_validate(case["application"])
    result = CaseResult(
        case=str(case["case"]),
        photo=str(case["photo"]),
        expected_status=str(case["expected_status"]),
        got_status=None,
        seconds=seconds,
        error=error,
    )
    if reading is None:
        return result

    got: VerificationReport = verify(application, reading)
    result.got_status = got.status.value
    if case["truth"] is None:
        return result

    truth = LabelExtraction.model_validate(case["truth"])
    expected = verify(application, truth)
    for want, have in zip(expected.fields, got.fields, strict=True):
        result.fields_total += 1
        if want.verdict == have.verdict:
            result.fields_right += 1
        else:
            result.wrong_fields.append(f"{want.field}: {want.verdict} -> {have.verdict}")

    for name in READ_FIELDS:
        result.text_total += 1
        result.text_exact += getattr(truth, name).text == getattr(reading, name).text
    result.text_total += 1
    result.text_exact += truth.government_warning.full_text == reading.government_warning.full_text
    return result


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


def summarize(results: list[CaseResult]) -> dict[str, float | int]:
    def share(part: int, whole: int) -> float:
        return round(part / whole, 3) if whole else 0.0

    clean = [r for r in results if r.photo == "clean"]
    seconds = [r.seconds for r in results if r.error is None]
    return {
        "cases": len(results),
        "errors": sum(r.error is not None for r in results),
        "false_clear": sum(r.false_clear for r in results),
        "status_exact": share(sum(r.exact for r in results), len(results)),
        "status_exact_clean": share(sum(r.exact for r in clean), len(clean)),
        "status_acceptable": share(sum(r.acceptable for r in results), len(results)),
        "field_verdicts": share(
            sum(r.fields_right for r in results), sum(r.fields_total for r in results)
        ),
        "text_exact": share(sum(r.text_exact for r in results), sum(r.text_total for r in results)),
        "latency_p50_s": round(statistics.median(seconds), 2) if seconds else 0.0,
        "latency_p95_s": round(_percentile(seconds, 95), 2),
        "latency_max_s": round(max(seconds), 2) if seconds else 0.0,
    }
