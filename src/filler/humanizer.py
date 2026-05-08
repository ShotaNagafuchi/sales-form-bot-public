"""Human-like interaction patterns: typing delays, cursor jitter, natural scroll."""

from __future__ import annotations

import random

from playwright.async_api import Page


async def human_type(page: Page, selector: str, text: str) -> None:
    """Type text with human-like delays (50-150ms per character)."""
    element = await page.wait_for_selector(selector, timeout=10_000)
    await element.click()
    await _random_pause(page, 200, 500)

    for char in text:
        await page.keyboard.type(char, delay=random.randint(50, 150))
        # Occasional longer pause mid-typing (simulates thinking)
        if random.random() < 0.05:
            await _random_pause(page, 300, 800)


async def human_click(page: Page, selector: str) -> None:
    """Click with small random offset to simulate imprecise cursor."""
    element = await page.wait_for_selector(selector, timeout=10_000)
    box = await element.bounding_box()
    if box:
        # Click within element bounds with slight random offset
        x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
        y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
        await page.mouse.click(x, y)
    else:
        await element.click()


async def human_select(page: Page, selector: str, option_text: str) -> None:
    """Select a dropdown option with human-like interaction."""
    element = await page.wait_for_selector(selector, timeout=10_000)
    await element.click()
    await _random_pause(page, 300, 700)
    await element.select_option(label=option_text)


async def scroll_to_element(page: Page, selector: str) -> None:
    """Scroll element into view with natural behavior."""
    element = await page.wait_for_selector(selector, timeout=10_000)
    await element.scroll_into_view_if_needed()
    await _random_pause(page, 200, 500)


async def inter_field_pause(page: Page) -> None:
    """Pause between fields (500-2000ms)."""
    await _random_pause(page, 500, 2000)


async def _random_pause(page: Page, min_ms: int, max_ms: int) -> None:
    await page.wait_for_timeout(random.randint(min_ms, max_ms))
