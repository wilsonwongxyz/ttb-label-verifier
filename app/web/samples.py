"""The built-in example labels offered by "Try an example" (see scripts/make_samples.py)."""

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.rules.models import ApplicationData


@dataclass(frozen=True)
class Sample:
    name: str
    title: str
    file: str
    application: ApplicationData


@lru_cache
def load_samples(directory: Path) -> dict[str, Sample]:
    index = json.loads((directory / "fixtures.json").read_text())
    return {
        entry["name"]: Sample(
            name=entry["name"],
            title=entry["title"],
            file=entry["file"],
            application=ApplicationData.model_validate(entry["application"]),
        )
        for entry in index["samples"]
    }
