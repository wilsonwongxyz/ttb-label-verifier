"""Access to the synthetic sample labels in app/samples (see scripts/make_samples.py)."""

import json
from pathlib import Path
from typing import Any

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "app" / "samples"


def sample_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = json.loads((SAMPLES_DIR / "fixtures.json").read_text())[
        "samples"
    ]
    return entries


def sample(name: str) -> dict[str, Any]:
    return next(entry for entry in sample_entries() if entry["name"] == name)


def sample_bytes(name: str) -> bytes:
    return (SAMPLES_DIR / sample(name)["file"]).read_bytes()
