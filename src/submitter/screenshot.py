"""Screenshot capture before/after form submission."""

from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page


async def take_screenshot(page: Page, output_path: str) -> str:
    """Take a full-page screenshot and save to output_path. Returns the path."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=output_path, full_page=True)
    return output_path
