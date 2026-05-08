"""Playwright form filling engine: takes validated mappings and fills the form."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from src.detector.models import FieldType
from src.filler.humanizer import (
    human_click,
    human_select,
    human_type,
    inter_field_pause,
    scroll_to_element,
)
from src.mapper.validator import ValidatedMapping


@dataclass(frozen=True)
class FillResult:
    filled: list[str]
    skipped: list[str]
    errors: list[str]


async def fill_form(
    page: Page,
    mappings: list[ValidatedMapping],
    humanize: bool = True,
) -> FillResult:
    """Fill form fields using validated mappings.

    Args:
        page: Playwright page with the form loaded.
        mappings: Validated and normalized field mappings.
        humanize: Whether to use human-like delays and interactions.
    """
    filled: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for mapping in mappings:
        try:
            success = await _fill_field(page, mapping, humanize)
            if success:
                filled.append(mapping.field_name)
            else:
                skipped.append(mapping.field_name)

            if humanize:
                await inter_field_pause(page)

        except Exception as e:
            errors.append(f"{mapping.field_name}: {e}")

    return FillResult(filled=filled, skipped=skipped, errors=errors)


async def _fill_field(
    page: Page,
    mapping: ValidatedMapping,
    humanize: bool,
) -> bool:
    """Fill a single form field. Returns True if successful."""
    selector = mapping.field_selector
    if not selector:
        return False

    # Check element exists
    element = await page.query_selector(selector)
    if element is None:
        return False

    await scroll_to_element(page, selector)

    match mapping.field_type:
        case FieldType.TEXT | FieldType.EMAIL | FieldType.TEL | FieldType.URL | FieldType.NUMBER | FieldType.PASSWORD:
            await _fill_text_input(page, selector, mapping.normalized_value, humanize)

        case FieldType.TEXTAREA:
            await _fill_text_input(page, selector, mapping.normalized_value, humanize)

        case FieldType.SELECT:
            await _fill_select(page, selector, mapping.normalized_value, humanize)

        case FieldType.CHECKBOX:
            await _fill_checkbox(page, selector, humanize)

        case FieldType.RADIO:
            await _fill_radio(page, selector, mapping.normalized_value, humanize)

        case _:
            return False

    return True


async def _fill_text_input(
    page: Page, selector: str, value: str, humanize: bool
) -> None:
    """Clear and type into a text input or textarea."""
    # Focus and clear existing value
    element = await page.query_selector(selector)
    await element.click()
    await page.keyboard.press("Meta+a")
    await page.keyboard.press("Backspace")

    if humanize:
        await human_type(page, selector, value)
    else:
        await page.fill(selector, value)


async def _fill_select(
    page: Page, selector: str, value: str, humanize: bool
) -> None:
    """Select an option from a dropdown."""
    if humanize:
        await human_select(page, selector, value)
    else:
        element = await page.query_selector(selector)
        await element.select_option(label=value)


async def _fill_checkbox(page: Page, selector: str, humanize: bool) -> None:
    """Check a checkbox if not already checked."""
    is_checked = await page.is_checked(selector)
    if not is_checked:
        if humanize:
            await human_click(page, selector)
        else:
            await page.check(selector)


async def _fill_radio(
    page: Page, selector: str, value: str, humanize: bool
) -> None:
    """Select a radio button by value."""
    # Try to find radio with matching value
    radio_selector = f'{selector}[value="{value}"]'
    element = await page.query_selector(radio_selector)
    if element:
        if humanize:
            await human_click(page, radio_selector)
        else:
            await element.check()
    else:
        # Fallback: click the base selector
        if humanize:
            await human_click(page, selector)
        else:
            await page.check(selector)
