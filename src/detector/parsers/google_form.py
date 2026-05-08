"""Google Forms extraction.

Google Forms use a specific DOM structure with data-params attributes
and are typically embedded in iframes.
"""

from __future__ import annotations

from playwright.async_api import Page

from src.detector.models import DetectedForm, FieldType, FormField, FormType


async def parse_google_form(page: Page, url: str) -> list[DetectedForm]:
    """Extract fields from Google Forms pages."""
    # Check if this is a Google Form
    is_google_form = await page.evaluate(
        """() => {
            return document.querySelector('form[action*="docs.google.com/forms"]') !== null
                || window.location.hostname === 'docs.google.com';
        }"""
    )
    if not is_google_form:
        return []

    # Google Forms use div[data-params] for each question
    question_els = await page.query_selector_all("[data-params]")
    if not question_els:
        # Try the newer structure with role="listitem"
        question_els = await page.query_selector_all('div[role="listitem"]')

    fields: list[FormField] = []
    for q_el in question_els:
        field = await _extract_google_field(page, q_el)
        if field is not None:
            fields.append(field)

    if not fields:
        return []

    return [
        DetectedForm(
            url=url,
            form_type=FormType.GOOGLE_FORM,
            fields=fields,
            submit_selector='div[role="button"]:has-text("送信"), div[role="button"]:has-text("Submit")',
            form_selector="form",
        )
    ]


async def _extract_google_field(page: Page, q_el) -> FormField | None:
    """Extract a single field from a Google Forms question block."""
    # Get the question title
    label = await q_el.evaluate(
        """(el) => {
            const title = el.querySelector('[role="heading"]')
                || el.querySelector('.freebirdFormviewItemItemHeader');
            return title ? title.innerText.trim() : '';
        }"""
    )
    if not label:
        return None

    # Detect field type from the input element
    input_el = await q_el.query_selector("input[type='text'], input[type='email']")
    textarea_el = await q_el.query_selector("textarea")
    select_el = await q_el.query_selector('[role="listbox"]')
    radio_el = await q_el.query_selector('[role="radio"]')
    checkbox_el = await q_el.query_selector('[role="checkbox"]')

    if textarea_el:
        field_type = FieldType.TEXTAREA
        name = await textarea_el.get_attribute("name") or ""
        selector = f'textarea[name="{name}"]' if name else ""
    elif select_el:
        field_type = FieldType.SELECT
        name = ""
        selector = ""
    elif radio_el:
        field_type = FieldType.RADIO
        name = ""
        selector = ""
    elif checkbox_el:
        field_type = FieldType.CHECKBOX
        name = ""
        selector = ""
    elif input_el:
        input_type = (await input_el.get_attribute("type") or "text").lower()
        field_type = FieldType.EMAIL if input_type == "email" else FieldType.TEXT
        name = await input_el.get_attribute("name") or ""
        selector = f'input[name="{name}"]' if name else ""
    else:
        return None

    required = await q_el.evaluate(
        "(el) => el.querySelector('[aria-required=\"true\"]') !== null"
    )

    return FormField(
        name=name,
        field_type=field_type,
        label=label,
        required=required,
        selector=selector,
    )
