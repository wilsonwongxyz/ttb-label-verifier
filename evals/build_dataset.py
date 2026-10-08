"""Build the evaluation set: labels with planted defects, each as a clean scan and as phone photos.

Writes ``evals/dataset/<case>.jpg`` and ``evals/dataset/cases.jsonl``. Each case records the
application, the exact text printed on the label (ground truth), the expected overall status,
and how the photo was degraded. Run from the repo root:

    uv run python -m evals.build_dataset

Deterministic: the same Pillow version produces the same images.
"""

import io
import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.extract.schema import LabelExtraction
from app.rules import verify
from app.rules.models import ApplicationData
from app.rules.warning import REQUIRED_WARNING
from scripts.make_samples import SAMPLES, font, reading, render

OUT_DIR = Path(__file__).resolve().parent / "dataset"
BODY = REQUIRED_WARNING.removeprefix("GOVERNMENT WARNING: ")


def _spirits(name: str, brand: str, class_type: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": name,
        "colors": ("#f2efe6", "#2b2b2b"),
        "brand": brand,
        "class_type": class_type,
        "alcohol": "40% Alc./Vol. (80 Proof)",
        "net": "750 mL",
        "bottler": f"Bottled by {brand.title()} Distilling Co., Louisville, Kentucky",
        "origin": None,
        "prefix": "GOVERNMENT WARNING:",
        "prefix_bold": True,
        "body": BODY,
    }
    application = {
        "beverage_type": "distilled_spirits",
        "brand_name": brand,
        "class_type": class_type,
        "alcohol_content": base["alcohol"],
        "net_contents": base["net"],
        "bottler_name_address": base["bottler"],
        "imported": False,
        "country_of_origin": None,
    }
    label_overrides = {k: v for k, v in overrides.items() if k != "application"}
    base.update(label_overrides)
    application.update(overrides.get("application", {}))
    base["application"] = application
    return base


# Defects beyond the five demo samples, one per label.
EXTRA_LABELS: list[dict[str, Any]] = [
    _spirits(
        "granite_peak_proof_mismatch",
        "GRANITE PEAK",
        "Straight Rye Whiskey",
        alcohol="45% Alc./Vol. (95 Proof)",
        application={"alcohol_content": "45% Alc./Vol. (90 Proof)"},
    ),
    _spirits(
        "blue_heron_truncated_warning",
        "BLUE HERON",
        "Silver Tequila",
        body=BODY.split(" (2)")[0],
    ),
    _spirits("night_owl_missing_warning", "NIGHT OWL", "Coffee Liqueur", body=None, prefix=None),
    _spirits(
        "silver_creek_net_contents",
        "SILVER CREEK",
        "Blended Whiskey",
        net="700 mL",
        application={"net_contents": "750 mL"},
    ),
    _spirits(
        "maple_hollow_brand_typo",
        "MAPLE HOLOW",
        "Maple Flavored Whiskey",
        application={"brand_name": "MAPLE HOLLOW"},
    ),
    {
        **_spirits("hop_harbor_ipa_no_abv", "HOP HARBOR", "India Pale Ale", alcohol=None),
        "net": "12 FL OZ",
        "bottler": "Brewed and canned by Hop Harbor Brewing, Portland, Maine",
        "application": {
            "beverage_type": "malt_beverage",
            "brand_name": "HOP HARBOR",
            "class_type": "India Pale Ale",
            "alcohol_content": None,
            "net_contents": "12 fl oz",
            "bottler_name_address": "Brewed and canned by Hop Harbor Brewing, Portland, Maine",
            "imported": False,
            "country_of_origin": None,
        },
    },
]


# --- Photo degradations -------------------------------------------------------------------


def _on_counter(label: Image.Image, rng: random.Random) -> Image.Image:
    """Place the label on a darker background, like a photo of a bottle on a counter."""
    pad = 120
    shade = rng.randint(60, 110)
    canvas = Image.new(
        "RGB", (label.width + 2 * pad, label.height + 2 * pad), (shade, shade - 10, shade - 20)
    )
    canvas.paste(label, (pad, pad))
    return canvas


def angled(label: Image.Image, rng: random.Random) -> Image.Image:
    photo = _on_counter(label, rng)
    return photo.rotate(
        rng.choice([-8, -6, 6, 8]), resample=Image.Resampling.BICUBIC, fillcolor=(70, 60, 50)
    )


def glare(label: Image.Image, rng: random.Random) -> Image.Image:
    photo = _on_counter(label, rng).convert("RGBA")
    overlay = Image.new("RGBA", photo.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = int(photo.width * rng.uniform(0.55, 0.75)), int(photo.height * rng.uniform(0.25, 0.45))
    draw.ellipse((cx - 150, cy - 220, cx + 150, cy + 220), fill=(255, 255, 255, 170))
    overlay = overlay.filter(ImageFilter.GaussianBlur(60))
    return Image.alpha_composite(photo, overlay).convert("RGB")


def blurry(label: Image.Image, rng: random.Random) -> Image.Image:
    return _on_counter(label, rng).filter(ImageFilter.GaussianBlur(1.6))


def dim(label: Image.Image, rng: random.Random) -> Image.Image:
    photo = ImageEnhance.Brightness(_on_counter(label, rng)).enhance(0.45)
    noise = Image.effect_noise(photo.size, 18).convert("RGB")
    return Image.blend(photo, noise, 0.08)


def compressed(label: Image.Image, rng: random.Random) -> Image.Image:
    photo = _on_counter(label, rng)
    small = photo.resize((photo.width // 2, photo.height // 2), Image.Resampling.BILINEAR)
    out = io.BytesIO()
    small.save(out, format="JPEG", quality=25)
    return Image.open(io.BytesIO(out.getvalue())).convert("RGB")


DEGRADATIONS = {
    "angled": angled,
    "glare": glare,
    "blurry": blurry,
    "dim": dim,
    "compressed": compressed,
}


def not_a_label() -> Image.Image:
    image = Image.new("RGB", (1000, 1300), "#fdfdf8")
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "Grocery list", font=font("DejaVuSans-Bold.ttf", 54), fill="#223")
    for n, item in enumerate(["milk", "eggs", "bread", "apples", "coffee", "rice"]):
        draw.text((100, 220 + 90 * n), f"• {item}", font=font("DejaVuSans.ttf", 44), fill="#334")
    return image


def expected_status(label: dict[str, Any]) -> str:
    application = ApplicationData.model_validate(label["application"])
    return verify(application, LabelExtraction.model_validate(reading(label))).status.value


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261008)
    names = list(DEGRADATIONS)
    cases: list[dict[str, Any]] = []

    for n, label in enumerate([*SAMPLES, *EXTRA_LABELS]):
        clean = render(label)
        variants = [("clean", clean)] + [
            (kind, DEGRADATIONS[kind](clean, rng)) for kind in (names[n % 5], names[(n + 2) % 5])
        ]
        for kind, image in variants:
            case = f"{label['name']}__{kind}"
            image.save(OUT_DIR / f"{case}.jpg", format="JPEG", quality=88)
            cases.append(
                {
                    "case": case,
                    "label": label["name"],
                    "photo": kind,
                    "file": f"{case}.jpg",
                    "application": label["application"],
                    "truth": reading(label),
                    "expected_status": expected_status(label),
                }
            )

    not_a_label().save(OUT_DIR / "grocery_list__clean.jpg", format="JPEG", quality=88)
    cases.append(
        {
            "case": "grocery_list__clean",
            "label": "grocery_list",
            "photo": "clean",
            "file": "grocery_list__clean.jpg",
            "application": SAMPLES[0]["application"],
            "truth": None,
            "expected_status": "cant_read",
        }
    )

    with (OUT_DIR / "cases.jsonl").open("w") as out:
        for entry in cases:
            out.write(json.dumps(entry) + "\n")
    print(f"Wrote {len(cases)} cases to {OUT_DIR}")


if __name__ == "__main__":
    main()
