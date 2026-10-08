"""Run the evaluation set through the real pipeline and report accuracy, latency and cost.

    uv run python -m evals.run                                 # Claude, settings from LV_*
    uv run python -m evals.run --model claude-sonnet-5-5 --runs 2
    uv run python -m evals.run --extractor oracle              # offline harness check

The ``claude`` extractor costs money (about $0.02 for one pass on Haiku 5.5). Results go to
``evals/results/`` (git-ignored) and a one-line summary is appended to ``evals/RESULTS.md``.
"""

import argparse
import asyncio
import datetime as dt
import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.config import Settings
from app.extract.base import ExtractionError, LabelExtractor
from app.extract.claude import ClaudeExtractor
from app.extract.prompt import PROMPT_VERSION
from app.extract.schema import LabelExtraction
from app.imaging.prepare import ImageRejectedError, PreparedImage, prepare_image
from app.rules.models import ApplicationData, BeverageType
from evals.grading import CaseResult, grade, summarize

HERE = Path(__file__).resolve().parent
DATASET = HERE / "dataset"

# USD per million tokens (input, output); see the Claude pricing page.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


class OracleExtractor:
    """Returns the ground truth: checks the harness and rules without calling a model."""

    def __init__(self, cases: list[dict[str, Any]]) -> None:
        self._truth = {}
        for case in cases:
            raw = (DATASET / case["file"]).read_bytes()
            sha = prepare_image(raw, max_bytes=50 * 1024 * 1024).source_sha256
            self._truth[sha] = case["truth"]

    async def extract(self, image: PreparedImage, beverage_type: BeverageType) -> LabelExtraction:
        truth = self._truth[image.source_sha256]
        if truth is None:
            return LabelExtraction.unreadable().model_copy(
                update={"is_alcohol_label": False, "image_quality": "unusable"}
            )
        return LabelExtraction.model_validate(truth)


def load_cases(match: str = "") -> list[dict[str, Any]]:
    with (DATASET / "cases.jsonl").open() as lines:
        cases = [json.loads(line) for line in lines]
    return [c for c in cases if match in c["case"]]


async def run_case(
    case: dict[str, Any], extractor: LabelExtractor, settings: Settings, limit: asyncio.Semaphore
) -> CaseResult:
    async with limit:
        raw = (DATASET / case["file"]).read_bytes()
        application = ApplicationData.model_validate(case["application"])
        started = time.perf_counter()
        try:
            image = prepare_image(raw, max_bytes=settings.max_image_bytes)
            reading = await extractor.extract(image, application.beverage_type)
        except (ExtractionError, ImageRejectedError) as exc:
            return grade(case, None, time.perf_counter() - started, error=exc.message)
        return grade(case, reading, time.perf_counter() - started)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--extractor", choices=["claude", "oracle"], default="claude")
    parser.add_argument("--model", help="override LV_MODEL")
    parser.add_argument("--effort", choices=["low", "medium", "high"], help="override LV_EFFORT")
    parser.add_argument("--runs", type=int, default=1, help="passes over the dataset")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--match", default="", help="only cases whose name contains this")
    parser.add_argument("--no-log", action="store_true", help="don't append to RESULTS.md")
    args = parser.parse_args()

    overrides = {k: v for k, v in {"model": args.model, "effort": args.effort}.items() if v}
    settings = Settings(**overrides)
    cases = load_cases(args.match)
    extractor: LabelExtractor
    if args.extractor == "oracle":
        extractor = OracleExtractor(cases)
        label = "oracle"
    else:
        extractor = ClaudeExtractor.from_settings(settings)
        label = f"{settings.model} effort={settings.effort}"

    limit = asyncio.Semaphore(args.concurrency)
    results: list[CaseResult] = []
    for _ in range(args.runs):
        results += await asyncio.gather(*(run_case(c, extractor, settings, limit) for c in cases))

    summary: dict[str, Any] = summarize(results)
    if isinstance(extractor, ClaudeExtractor) and extractor.calls:
        price_in, price_out = PRICES.get(settings.model, (0.0, 0.0))
        cost = (extractor.input_tokens * price_in + extractor.output_tokens * price_out) / 1e6
        summary["cost_usd"] = round(cost, 4)
        summary["cost_per_label_usd"] = round(cost / extractor.calls, 5)

    print(f"\n{label}  prompt={PROMPT_VERSION}  cases={len(cases)} x {args.runs} runs\n")
    for result in results:
        if not result.acceptable or result.false_clear or result.error:
            flag = "FALSE CLEAR" if result.false_clear else ("ERROR" if result.error else "WRONG")
            print(
                f"  {flag:11} {result.case}: expected {result.expected_status}, "
                f"got {result.got_status} ({result.error or ', '.join(result.wrong_fields)})"
            )
    print()
    for key, value in summary.items():
        print(f"  {key:22} {value}")

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{stamp}-{label.split()[0]}.json").write_text(
        json.dumps(
            {
                "extractor": label,
                "prompt_version": PROMPT_VERSION,
                "runs": args.runs,
                "summary": summary,
                "cases": [asdict(r) for r in results],
            },
            indent=2,
        )
    )
    if not args.no_log and args.extractor == "claude":
        with (HERE / "RESULTS.md").open("a") as log:
            log.write(
                f"| {stamp[:8]} | {label} | {PROMPT_VERSION} | {len(results)} | "
                f"{summary['false_clear']} | {summary['status_exact']:.0%} | "
                f"{summary['status_acceptable']:.0%} | {summary['field_verdicts']:.0%} | "
                f"{summary['latency_p50_s']} | {summary['latency_p95_s']} | "
                f"{summary.get('cost_per_label_usd', '')} |\n"
            )


if __name__ == "__main__":
    asyncio.run(main())
