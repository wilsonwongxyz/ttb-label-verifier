"""Draw the synthetic sample labels and record what each one says.

Writes ``app/samples/<name>.png`` and ``app/samples/fixtures.json``. Each fixture holds the
application a reviewer would check the label against and the exact reading of the label
(its ground truth), keyed by the PNG's SHA-256. The offline demo and the tests replay these
readings through ``FixtureExtractor``; the evaluation set reuses them as ground truth.

Run from the repo root: ``uv run python scripts/make_samples.py``. Needs the DejaVu fonts.
Regenerating changes the PNG bytes (and hashes) only if Pillow's output changes.
"""

import hashlib
import json
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.rules.warning import REQUIRED_WARNING

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
OUT_DIR = Path(__file__).resolve().parent.parent / "app" / "samples"
BODY = REQUIRED_WARNING.removeprefix("GOVERNMENT WARNING: ")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


SAMPLES: list[dict[str, Any]] = [
    {
        "name": "old_tom_bourbon",
        "title": "Old Tom bourbon (everything matches)",
        "colors": ("#f4ead5", "#5b3a1a"),
        "brand": "OLD TOM DISTILLERY",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "alcohol": "45% Alc./Vol. (90 Proof)",
        "net": "750 mL",
        "bottler": "Bottled by Old Tom Distillery, Bardstown, Kentucky",
        "origin": None,
        "prefix": "GOVERNMENT WARNING:",
        "prefix_bold": True,
        "body": BODY,
        "application": {
            "beverage_type": "distilled_spirits",
            "brand_name": "OLD TOM DISTILLERY",
            "class_type": "Kentucky Straight Bourbon Whiskey",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "bottler_name_address": "Bottled by Old Tom Distillery, Bardstown, Kentucky",
            "imported": False,
            "country_of_origin": None,
        },
    },
    {
        "name": "stones_throw_gin",
        "title": "Stone's Throw gin (brand in capitals on the label)",
        "colors": ("#e8f0ec", "#1f4d3a"),
        "brand": "STONE'S THROW",
        "class_type": "London Dry Gin",
        "alcohol": "Alc. 41.5% by Vol.",
        "net": "750 mL",
        "bottler": "Distilled and bottled by Stone's Throw Spirits, Portland, Oregon",
        "origin": None,
        "prefix": "GOVERNMENT WARNING:",
        "prefix_bold": True,
        "body": BODY,
        "application": {
            "beverage_type": "distilled_spirits",
            "brand_name": "Stone's Throw",
            "class_type": "London Dry Gin",
            "alcohol_content": "41.5% Alc./Vol.",
            "net_contents": "750 mL",
            "bottler_name_address": "Distilled and bottled by Stone's Throw Spirits, "
            "Portland, Oregon",
            "imported": False,
            "country_of_origin": None,
        },
    },
    {
        "name": "harbor_light_rum_title_case",
        "title": "Harbor Light rum (warning lead-in in title case)",
        "colors": ("#eaf2f8", "#123c5a"),
        "brand": "HARBOR LIGHT",
        "class_type": "Gold Rum",
        "alcohol": "40% Alc./Vol. (80 Proof)",
        "net": "1 L",
        "bottler": "Bottled by Harbor Light Rum Co., Key West, Florida",
        "origin": None,
        "prefix": "Government Warning:",
        "prefix_bold": False,
        "body": BODY,
        "application": {
            "beverage_type": "distilled_spirits",
            "brand_name": "HARBOR LIGHT",
            "class_type": "Gold Rum",
            "alcohol_content": "40% Alc./Vol. (80 Proof)",
            "net_contents": "1 L",
            "bottler_name_address": "Bottled by Harbor Light Rum Co., Key West, Florida",
            "imported": False,
            "country_of_origin": None,
        },
    },
    {
        "name": "copper_ridge_vodka_wrong_abv",
        "title": "Copper Ridge vodka (alcohol content differs)",
        "colors": ("#f7efe9", "#7a3b16"),
        "brand": "COPPER RIDGE",
        "class_type": "Vodka",
        "alcohol": "40% Alc./Vol. (80 Proof)",
        "net": "750 mL",
        "bottler": "Bottled by Copper Ridge Distilling, Boise, Idaho",
        "origin": None,
        "prefix": "GOVERNMENT WARNING:",
        "prefix_bold": True,
        "body": BODY,
        "application": {
            "beverage_type": "distilled_spirits",
            "brand_name": "COPPER RIDGE",
            "class_type": "Vodka",
            "alcohol_content": "45% Alc./Vol. (90 Proof)",
            "net_contents": "750 mL",
            "bottler_name_address": "Bottled by Copper Ridge Distilling, Boise, Idaho",
            "imported": False,
            "country_of_origin": None,
        },
    },
    {
        "name": "domaine_viale_wine_reworded",
        "title": "Domaine Viale wine (imported; warning reworded)",
        "colors": ("#f5ecf0", "#5e1a35"),
        "brand": "DOMAINE VIALE",
        "class_type": "Red Wine",
        "alcohol": "13.5% Alc./Vol.",
        "net": "75 cL",
        "bottler": "Imported by Viale Imports LLC, New York, NY",
        "origin": "Product of France",
        "prefix": "GOVERNMENT WARNING:",
        "prefix_bold": True,
        "body": BODY.replace("should not drink", "should avoid drinking"),
        "application": {
            "beverage_type": "wine",
            "brand_name": "DOMAINE VIALE",
            "class_type": "Red Wine",
            "alcohol_content": "13.5% Alc./Vol.",
            "net_contents": "750 mL",
            "bottler_name_address": "Imported by Viale Imports LLC, New York, NY",
            "imported": True,
            "country_of_origin": "Product of France",
        },
    },
]

WIDTH, HEIGHT, MARGIN = 900, 1200, 70


def centered(draw: ImageDraw.ImageDraw, y: float, text: str, face: Any, fill: str) -> float:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=face)
    draw.text(((WIDTH - (right - left)) / 2, y), text, font=face, fill=fill)
    return y + (bottom - top)


def render(sample: dict[str, Any]) -> Image.Image:
    paper, ink = sample["colors"]
    image = Image.new("RGB", (WIDTH, HEIGHT), paper)
    draw = ImageDraw.Draw(image)
    draw.rectangle((25, 25, WIDTH - 25, HEIGHT - 25), outline=ink, width=6)
    draw.rectangle((40, 40, WIDTH - 40, HEIGHT - 40), outline=ink, width=2)

    y: float = 130
    y = centered(draw, y, sample["brand"], font("DejaVuSerif-Bold.ttf", 64), ink) + 40
    y = centered(draw, y, sample["class_type"], font("DejaVuSerif.ttf", 34), ink) + 90
    if sample["alcohol"]:
        y = centered(draw, y, sample["alcohol"], font("DejaVuSans-Bold.ttf", 34), ink) + 30
    y = centered(draw, y, sample["net"], font("DejaVuSans.ttf", 34), ink) + 80
    small = font("DejaVuSans.ttf", 22)
    for line in textwrap.wrap(sample["bottler"], 60):
        y = centered(draw, y, line, small, ink) + 10
    if sample["origin"]:
        y = centered(draw, y + 10, sample["origin"], font("DejaVuSans-Bold.ttf", 24), ink) + 10

    if sample["body"] is None:  # a label with no health warning at all
        return image
    y = HEIGHT - 300
    prefix_font = font("DejaVuSans-Bold.ttf" if sample["prefix_bold"] else "DejaVuSans.ttf", 20)
    draw.text((MARGIN, y), sample["prefix"], font=prefix_font, fill=ink)
    y += 30
    for line in textwrap.wrap(sample["body"], 72):
        draw.text((MARGIN, y), line, font=font("DejaVuSans.ttf", 20), fill=ink)
        y += 26
    return image


def reading(sample: dict[str, Any]) -> dict[str, Any]:
    def value(text: str | None) -> dict[str, Any]:
        return {"text": text, "legibility": "clear" if text else "absent"}

    return {
        "is_alcohol_label": True,
        "image_quality": "good",
        "quality_issues": [],
        "brand_name": value(sample["brand"]),
        "class_type": value(sample["class_type"]),
        "alcohol_content": value(sample["alcohol"]),
        "net_contents": value(sample["net"]),
        "bottler_name_address": value(sample["bottler"]),
        "country_of_origin": value(sample["origin"]),
        "government_warning": {
            "full_text": f"{sample['prefix']} {sample['body']}",
            "prefix_as_printed": sample["prefix"],
            "prefix_looks_bold": "yes" if sample["prefix_bold"] else "no",
            "legibility": "clear",
        }
        if sample["body"] is not None
        else {
            "full_text": None,
            "prefix_as_printed": None,
            "prefix_looks_bold": "unsure",
            "legibility": "absent",
        },
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries = []
    for sample in SAMPLES:
        path = OUT_DIR / f"{sample['name']}.png"
        render(sample).save(path, format="PNG", optimize=True)
        entries.append(
            {
                "name": sample["name"],
                "title": sample["title"],
                "file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "application": sample["application"],
                "extraction": reading(sample),
            }
        )
    (OUT_DIR / "fixtures.json").write_text(json.dumps({"samples": entries}, indent=2) + "\n")
    print(f"Wrote {len(entries)} samples to {OUT_DIR}")


if __name__ == "__main__":
    main()
