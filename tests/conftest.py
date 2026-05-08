from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sample_forms"


@pytest_asyncio.fixture
async def browser():
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    yield browser
    await browser.close()
    await pw.stop()


@pytest_asyncio.fixture
async def page(browser):
    context = await browser.new_context(locale="ja-JP")
    page = await context.new_page()
    yield page
    await context.close()


def fixture_url(filename: str) -> str:
    """Return a file:// URL for a fixture HTML file."""
    return (FIXTURES_DIR / filename).as_uri()
