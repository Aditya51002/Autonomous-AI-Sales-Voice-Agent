"""Removes sensitive identifiers before text is stored."""

import re
from typing import Any

_PATTERNS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[email]"),
    (re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE), "[PAN]"),
    # Card, Aadhaar, account and phone numbers: nine or more digits, possibly grouped.
    (re.compile(r"(?<!\w)\+?\d(?:[ -]?\d){8,}(?!\w)"), "[number]"),
)


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_values(value: Any) -> Any:
    """Redact every string inside nested data, leaving numbers and keys alone."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_values(item) for item in value]
    return value
