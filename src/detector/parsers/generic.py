"""Generic HTML form parser — fallback for non-CMS forms."""

from __future__ import annotations

from playwright.async_api import Page

from src.detector.extractor import extract_forms
from src.detector.models import DetectedForm


async def parse_generic(page: Page, url: str) -> list[DetectedForm]:
    """Standard extraction — delegates to the core extractor."""
    return await extract_forms(page, url)
