"""Turkish first-letter capitals: str.upper turns i into I, losing the dot."""
from __future__ import annotations


def upper_first(text: str) -> str:
    """The first character in capital, Turkish way (i -> İ, ı -> I); the rest is untouched."""
    if not text:
        return text
    first = {"i": "İ", "ı": "I"}.get(text[0], text[0].upper())
    return first + text[1:]
