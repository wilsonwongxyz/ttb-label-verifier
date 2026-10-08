"""Run real extractions on the sample labels and compare them with the expected readings.

Costs real money (about $0.0005 per label on Claude Haiku 5.5). Needs LV_ANTHROPIC_API_KEY.

    uv run python scripts/smoke_extract.py                  # every sample
    uv run python scripts/smoke_extract.py old_tom_bourbon  # one sample
    LV_MODEL=claude-sonnet-5-5 uv run python scripts/smoke_extract.py
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from app.config import Settings
from app.extract.claude import ClaudeExtractor
from app.extract.schema import LabelExtraction
from app.imaging.prepare import prepare_image
from app.rules import verify
from app.rules.models import ApplicationData


async def main(names: list[str]) -> int:
    settings = Settings()
    extractor = ClaudeExtractor.from_settings(settings)
    samples_dir = settings.fixtures_dir
    entries = json.loads((samples_dir / "fixtures.json").read_text())["samples"]
    if names:
        entries = [e for e in entries if e["name"] in names]

    failures = 0
    print(f"model={settings.model} effort={settings.effort}\n")
    for entry in entries:
        image = prepare_image(
            (Path(samples_dir) / entry["file"]).read_bytes(), max_bytes=settings.max_image_bytes
        )
        application = ApplicationData.model_validate(entry["application"])
        started = time.perf_counter()
        reading = await extractor.extract(image, application.beverage_type)
        seconds = time.perf_counter() - started

        expected = LabelExtraction.model_validate(entry["extraction"])
        want = verify(application, expected).status
        got = verify(application, reading).status
        ok = want == got
        failures += not ok
        print(
            f"{'PASS' if ok else 'FAIL'} {entry['name']}: {got} (expected {want}), {seconds:.2f}s"
        )
        for field in LabelExtraction.model_fields:
            if getattr(reading, field) != getattr(expected, field):
                print(f"    {field}: got {getattr(reading, field)!r}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
