import hashlib
import io

import pytest
from PIL import Image, ImageDraw

from app.imaging.prepare import (
    MAX_LONG_EDGE,
    ImageRejectedError,
    prepare_image,
)

LIMIT = 10 * 1024 * 1024


def encode(image: Image.Image, fmt: str, **save_args: object) -> bytes:
    out = io.BytesIO()
    image.save(out, format=fmt, **save_args)
    return out.getvalue()


def label_like(size: tuple[int, int] = (900, 1200), mode: str = "RGB") -> Image.Image:
    image = Image.new(mode, size, "white")
    draw = ImageDraw.Draw(image)
    for y in range(20, size[1] - 20, 24):
        for x in range(20, size[0] - 60, 70):
            draw.rectangle((x, y, x + 40, y + 10), fill="black")
    return image


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_accepts_supported_formats_and_outputs_jpeg(fmt: str) -> None:
    prepared = prepare_image(encode(label_like(), fmt), max_bytes=LIMIT)
    assert prepared.media_type == "image/jpeg"
    with Image.open(io.BytesIO(prepared.data)) as out:
        assert out.format == "JPEG"
        assert out.size == (900, 1200)


def test_downscales_long_edge() -> None:
    prepared = prepare_image(encode(label_like((3000, 4000)), "PNG"), max_bytes=LIMIT)
    assert max(prepared.width, prepared.height) == MAX_LONG_EDGE
    assert (prepared.width, prepared.height) == (1176, 1568)


def test_applies_exif_rotation_and_strips_metadata() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90° clockwise
    exif[0x010F] = "PhoneMaker"  # camera make
    raw = encode(label_like((1200, 900)), "JPEG", exif=exif)
    prepared = prepare_image(raw, max_bytes=LIMIT)
    assert (prepared.width, prepared.height) == (900, 1200)
    with Image.open(io.BytesIO(prepared.data)) as out:
        assert len(out.getexif()) == 0


def test_transparent_png_is_flattened_onto_white() -> None:
    image = label_like(mode="RGBA")
    image.putpixel((0, 0), (0, 0, 0, 0))
    prepared = prepare_image(encode(image, "PNG"), max_bytes=LIMIT)
    with Image.open(io.BytesIO(prepared.data)) as out:
        assert out.mode == "RGB"
        assert out.getpixel((0, 0)) == pytest.approx((255, 255, 255), abs=3)


def test_source_hash_is_of_the_original_upload() -> None:
    raw = encode(label_like(), "PNG")
    assert prepare_image(raw, max_bytes=LIMIT).source_sha256 == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"", "The file is empty"),
        (b"%PDF-1.7 not an image", "isn't a photo we can open"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "isn't a photo we can open"),
    ],
)
def test_rejects_unusable_files(raw: bytes, message: str) -> None:
    with pytest.raises(ImageRejectedError, match=message):
        prepare_image(raw, max_bytes=LIMIT)


def test_rejects_unsupported_format() -> None:
    with pytest.raises(ImageRejectedError, match="GIF files aren't supported"):
        prepare_image(encode(label_like(), "GIF"), max_bytes=LIMIT)


def test_rejects_oversized_file() -> None:
    with pytest.raises(ImageRejectedError, match="larger than 1 MB"):
        prepare_image(b"x" * (1024 * 1024 + 1), max_bytes=1024 * 1024)


def test_rejects_tiny_image() -> None:
    with pytest.raises(ImageRejectedError, match="too small to read"):
        prepare_image(encode(label_like((200, 280)), "PNG"), max_bytes=LIMIT)


@pytest.mark.filterwarnings("ignore::PIL.Image.DecompressionBombWarning")
def test_rejects_decompression_bomb() -> None:
    # A tiny file that claims a huge canvas.
    raw = encode(Image.new("1", (10_000, 10_000)), "PNG")
    assert len(raw) < LIMIT
    with pytest.raises(ImageRejectedError, match="too large to process"):
        prepare_image(raw, max_bytes=LIMIT)


def test_rejects_extreme_decompression_bomb() -> None:
    # Large enough that Pillow itself refuses to open it.
    raw = encode(Image.new("1", (20_000, 20_000)), "PNG")
    with pytest.raises(ImageRejectedError, match="too large to process"):
        prepare_image(raw, max_bytes=LIMIT)
