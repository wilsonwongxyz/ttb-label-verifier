import asyncio
import json
from typing import Any

import pytest

from app.config import Settings
from app.extract.schema import LabelExtraction, ReadValue
from evals.grading import CaseResult, grade, summarize
from evals.run import DATASET, OracleExtractor, load_cases, run_case


def case(name: str, photo: str = "clean") -> dict[str, Any]:
    with (DATASET / "cases.jsonl").open() as lines:
        for line in lines:
            entry = json.loads(line)
            if entry["label"] == name and entry["photo"] == photo:
                return dict(entry)
    raise KeyError(name)


def result(expected: str, got: str | None, photo: str = "clean") -> CaseResult:
    return CaseResult(case="c", photo=photo, expected_status=expected, got_status=got, seconds=1.0)


@pytest.mark.parametrize(
    ("expected", "got", "photo", "exact", "acceptable", "false_clear"),
    [
        ("issues_found", "issues_found", "clean", True, True, False),
        ("issues_found", "all_clear", "clean", False, False, True),
        ("issues_found", "all_clear", "glare", False, False, True),
        ("issues_found", "needs_review", "glare", False, True, False),
        ("issues_found", "needs_review", "clean", False, False, False),
        ("all_clear", "cant_read", "blurry", False, True, False),
        ("all_clear", None, "clean", False, False, False),
    ],
)
def test_case_outcomes(
    expected: str, got: str | None, photo: str, exact: bool, acceptable: bool, false_clear: bool
) -> None:
    r = result(expected, got, photo)
    assert (r.exact, r.acceptable, r.false_clear) == (exact, acceptable, false_clear)


def test_grade_counts_field_and_text_accuracy() -> None:
    entry = case("copper_ridge_vodka_wrong_abv")
    reading = LabelExtraction.model_validate(entry["truth"])
    misread = reading.model_copy(
        update={"alcohol_content": ReadValue(text="45% Alc./Vol. (90 Proof)", legibility="clear")}
    )

    perfect = grade(entry, reading, 1.0)
    assert perfect.exact and perfect.fields_right == perfect.fields_total == 9
    assert perfect.text_exact == perfect.text_total == 7

    wrong = grade(entry, misread, 1.0)
    assert wrong.false_clear  # misreading the ABV hides the real problem
    assert wrong.wrong_fields == ["alcohol_content: mismatch -> match"]
    assert wrong.text_exact == 6


def test_summary() -> None:
    results = [result("all_clear", "all_clear"), result("issues_found", "all_clear", "glare")]
    results[1].seconds = 3.0
    summary = summarize(results)
    assert summary["false_clear"] == 1
    assert summary["status_exact"] == 0.5
    assert summary["latency_p95_s"] == 3.0


def test_oracle_scores_perfectly_on_the_whole_dataset() -> None:
    cases = load_cases()
    assert len(cases) >= 30
    extractor = OracleExtractor(cases)
    limit = asyncio.Semaphore(8)

    async def run_all() -> list[CaseResult]:
        settings = Settings(provider="fixture")
        return list(await asyncio.gather(*(run_case(c, extractor, settings, limit) for c in cases)))

    summary = summarize(asyncio.run(run_all()))
    assert summary["errors"] == 0
    assert summary["false_clear"] == 0
    assert summary["status_exact"] == 1.0
    assert summary["field_verdicts"] == 1.0
