"""Field-type specific value normalization."""

from __future__ import annotations

import re

from src.detector.models import FieldType


def normalize_value(value: str, field_type: FieldType) -> str:
    """Normalize a value based on the target field type."""
    if not value:
        return value

    match field_type:
        case FieldType.EMAIL:
            return _normalize_email(value)
        case FieldType.TEL:
            return _normalize_phone(value)
        case FieldType.URL:
            return _normalize_url(value)
        case _:
            return value.strip()


def _normalize_email(value: str) -> str:
    """Validate and clean email format."""
    cleaned = value.strip().lower()
    if re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", cleaned):
        return cleaned
    return value.strip()


def _normalize_phone(value: str) -> str:
    """Normalize Japanese phone numbers.

    Supports formats: 03-1234-5678, 090-1234-5678, 0312345678
    Preserves hyphens if present, adds them if missing for standard formats.
    """
    cleaned = re.sub(r"[\s　()]", "", value.strip())

    # Already has hyphens — keep as is
    if "-" in cleaned:
        return cleaned

    # Landline: 0X-XXXX-XXXX (10 digits starting with 0)
    if re.match(r"^0\d{9}$", cleaned):
        if cleaned.startswith("03") or cleaned.startswith("06"):
            return f"{cleaned[:2]}-{cleaned[2:6]}-{cleaned[6:]}"
        return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"

    # Mobile: 0X0-XXXX-XXXX (11 digits starting with 0)
    if re.match(r"^0\d{10}$", cleaned):
        return f"{cleaned[:3]}-{cleaned[3:7]}-{cleaned[7:]}"

    return cleaned


def _normalize_url(value: str) -> str:
    """Ensure URL has a scheme."""
    cleaned = value.strip()
    if cleaned and not cleaned.startswith(("http://", "https://")):
        return f"https://{cleaned}"
    return cleaned
