"""Turn an uploaded file into a small, clean JPEG the model can read quickly.

Validates the upload, fixes phone-camera rotation, strips all metadata (EXIF, GPS) and
downscales so the image costs about 1.6k tokens (TECHNICAL_DESIGN.md §4).
"""

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ACCEPTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
MAX_LONG_EDGE = 1568
MIN_SHORT_EDGE = 300
# Refuse images that would decode to more pixels than this (decompression-bomb guard).
MAX_PIXELS = 50_000_000
JPEG_QUALITY = 85


class ImageRejectedError(Exception):
    """The upload can't be used. ``message`` is safe to show to the user as is."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class PreparedImage:
    data: bytes
    width: int
    height: int
    source_sha256: str
    media_type: str = "image/jpeg"


def _flatten(image: Image.Image) -> Image.Image:
    """Convert to RGB, putting any transparency on white the way a label is printed."""
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def prepare_image(raw: bytes, *, max_bytes: int) -> PreparedImage:
    if not raw:
        raise ImageRejectedError("The file is empty. Please choose a photo of the label.")
    if len(raw) > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise ImageRejectedError(
            f"This file is larger than {limit_mb} MB. Please use a smaller photo."
        )

    try:
        with Image.open(io.BytesIO(raw)) as probe:
            fmt = probe.format or ""
            width, height = probe.size
            probe.verify()
    except Image.DecompressionBombError:
        raise ImageRejectedError(
            "This image is too large to process. Please use a smaller photo."
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise ImageRejectedError(
            "This file isn't a photo we can open. Please upload a JPG, PNG or WebP image."
        ) from None
    if fmt not in ACCEPTED_FORMATS:
        raise ImageRejectedError(
            f"{fmt or 'This'} files aren't supported. Please upload a JPG, PNG or WebP image."
        )
    if width * height > MAX_PIXELS:
        raise ImageRejectedError("This image is too large to process. Please use a smaller photo.")

    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = _flatten(ImageOps.exif_transpose(source))
    except (OSError, ValueError):
        raise ImageRejectedError(
            "This image appears to be damaged. Please upload it again or use another photo."
        ) from None

    if min(image.size) < MIN_SHORT_EDGE:
        raise ImageRejectedError(
            "This photo is too small to read. Please upload a larger or closer photo of the label."
        )

    image.thumbnail((MAX_LONG_EDGE, MAX_LONG_EDGE), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    # A fresh save without exif= drops every metadata block.
    image.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return PreparedImage(
        data=out.getvalue(),
        width=image.width,
        height=image.height,
        source_sha256=hashlib.sha256(raw).hexdigest(),
    )
