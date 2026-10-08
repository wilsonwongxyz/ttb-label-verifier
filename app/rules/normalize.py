"""Text normalization and diffing shared by the field rules."""

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher

from app.rules.models import DiffSpan

_QUOTES = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u02bc": "'",
        "`": "'",
        "\u00b4": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)
_APOSTROPHE = re.compile(r"'")
_AMPERSAND = re.compile(r"\s*&\s*")
_NON_WORD = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Unicode-normalize, straighten quotes and collapse whitespace. Case is preserved."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _WHITESPACE.sub(" ", text).strip()


def normalize(text: str) -> str:
    """Comparison key that ignores case, punctuation and spacing.

    "STONE'S THROW" and "Stone\u2019s Throw" both become "stones throw".
    """
    text = clean(text).casefold()
    text = _APOSTROPHE.sub("", text)
    text = _AMPERSAND.sub(" and ", text)
    text = _NON_WORD.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def is_blank(text: str | None) -> bool:
    return text is None or not text.strip()


def diff_spans(
    expected: Sequence[str],
    found: Sequence[str],
    *,
    key: Sequence[str] | None = None,
    found_key: Sequence[str] | None = None,
    sep: str = "",
) -> list[DiffSpan]:
    """Diff two token sequences, optionally matching on comparison keys but showing originals."""
    matcher = SequenceMatcher(
        a=list(key if key is not None else expected),
        b=list(found_key if found_key is not None else found),
        autojunk=False,
    )
    return [
        DiffSpan(op=op, expected=sep.join(expected[i1:i2]), found=sep.join(found[j1:j2]))
        for op, i1, i2, j1, j2 in matcher.get_opcodes()
    ]
