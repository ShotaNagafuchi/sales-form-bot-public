"""Contact Form 7 / WPForms-specific extraction.

CF7 forms use .wpcf7-form with <span class="wpcf7-form-control-wrap"> wrappers.
WPForms use .wpforms-form with .wpforms-field wrappers.
Both benefit from specialized label resolution.
"""

from __future__ import annotations

from playwright.async_api import Page

from src.detector.models import DetectedForm, FieldType, FormField, FormType


async def parse_cf7(page: Page, url: str) -> list[DetectedForm]:
    """Extract fields from Contact Form 7 forms."""
    form_els = await page.query_selector_all("form.wpcf7-form")
    if not form_els:
        return []

    forms: list[DetectedForm] = []

    for form_el in form_els:
        form_id = await form_el.get_attribute("id") or ""
        form_selector = f"#{form_id}" if form_id else "form.wpcf7-form"

        # CF7 wraps each field in a <p> or <div> with a <label>
        wraps = await form_el.query_selector_all(".wpcf7-form-control-wrap")
        fields: list[FormField] = []

        for wrap in wraps:
            field = await _extract_cf7_field(page, wrap)
            if field is not None:
                fields.append(field)

        submit_selector = f'{form_selector} input[type="submit"]'

        if fields:
            forms.append(
                DetectedForm(
                    url=url,
                    form_type=FormType.CONTACT_FORM_7,
                    fields=fields,
                    submit_selector=submit_selector,
                    form_selector=form_selector,
                )
            )

    return forms


async def _extract_cf7_field(page: Page, wrap_el) -> FormField | None:
    """Extract a single field from a CF7 control wrapper."""
    # Find the actual input/textarea/select inside the wrapper
    input_el = await wrap_el.query_selector("input, textarea, select")
    if input_el is None:
        return None

    tag = await input_el.evaluate("(el) => el.tagName.toLowerCase()")
    input_type = (await input_el.get_attribute("type") or "text").lower()

    if input_type in ("submit", "button", "hidden"):
        return None

    name = await input_el.get_attribute("name") or ""
    field_id = await input_el.get_attribute("id") or ""

    # CF7 label is usually the parent <label> or preceding <label>
    label = await page.evaluate(
        """(wrap) => {
            const p = wrap.closest('p') || wrap.closest('div') || wrap.parentElement;
            if (!p) return '';
            const lbl = p.querySelector('label');
            if (lbl) {
                const clone = lbl.cloneNode(true);
                clone.querySelectorAll('input,select,textarea,span.wpcf7-form-control-wrap')
                    .forEach(c => c.remove());
                return clone.innerText.trim();
            }
            return '';
        }""",
        wrap_el,
    )

    placeholder = await input_el.get_attribute("placeholder") or ""

    # Determine required from CF7 class
    wrap_class = await wrap_el.evaluate(
        "(el) => el.querySelector('[aria-required]')?.getAttribute('aria-required') || ''"
    )
    required = wrap_class == "true"

    if tag == "textarea":
        field_type = FieldType.TEXTAREA
    elif tag == "select":
        field_type = FieldType.SELECT
    elif input_type == "email":
        field_type = FieldType.EMAIL
    elif input_type == "tel":
        field_type = FieldType.TEL
    else:
        field_type = FieldType.TEXT

    options: list[str] = []
    if tag == "select":
        options = await input_el.evaluate(
            """(el) => Array.from(el.options)
                .filter(o => o.value !== '')
                .map(o => o.text.trim())"""
        )

    selector = f"#{field_id}" if field_id else f'[name="{name}"]'

    return FormField(
        name=name,
        field_type=field_type,
        label=label,
        placeholder=placeholder,
        required=required,
        options=options,
        selector=selector,
    )


async def parse_wpforms(page: Page, url: str) -> list[DetectedForm]:
    """Extract fields from WPForms forms."""
    form_els = await page.query_selector_all("form.wpforms-form")
    if not form_els:
        return []

    forms: list[DetectedForm] = []

    for form_el in form_els:
        form_id = await form_el.get_attribute("id") or ""
        form_selector = f"#{form_id}" if form_id else "form.wpforms-form"

        field_wraps = await form_el.query_selector_all(".wpforms-field")
        fields: list[FormField] = []

        for wrap in field_wraps:
            field = await _extract_wpforms_field(page, wrap)
            if field is not None:
                fields.append(field)

        submit_selector = f'{form_selector} button[type="submit"]'

        if fields:
            forms.append(
                DetectedForm(
                    url=url,
                    form_type=FormType.WPFORMS,
                    fields=fields,
                    submit_selector=submit_selector,
                    form_selector=form_selector,
                )
            )

    return forms


async def _extract_wpforms_field(page: Page, wrap_el) -> FormField | None:
    input_el = await wrap_el.query_selector("input, textarea, select")
    if input_el is None:
        return None

    tag = await input_el.evaluate("(el) => el.tagName.toLowerCase()")
    input_type = (await input_el.get_attribute("type") or "text").lower()

    if input_type in ("submit", "button", "hidden"):
        return None

    name = await input_el.get_attribute("name") or ""
    field_id = await input_el.get_attribute("id") or ""

    label = await wrap_el.evaluate(
        """(wrap) => {
            const lbl = wrap.querySelector('.wpforms-field-label, label');
            return lbl ? lbl.innerText.trim() : '';
        }"""
    )

    placeholder = await input_el.get_attribute("placeholder") or ""
    required = await wrap_el.evaluate(
        "(wrap) => wrap.classList.contains('wpforms-field-required')"
    )

    if tag == "textarea":
        field_type = FieldType.TEXTAREA
    elif tag == "select":
        field_type = FieldType.SELECT
    elif input_type == "email":
        field_type = FieldType.EMAIL
    elif input_type == "tel":
        field_type = FieldType.TEL
    else:
        field_type = FieldType.TEXT

    options: list[str] = []
    if tag == "select":
        options = await input_el.evaluate(
            """(el) => Array.from(el.options)
                .filter(o => o.value !== '')
                .map(o => o.text.trim())"""
        )

    selector = f"#{field_id}" if field_id else f'[name="{name}"]'

    return FormField(
        name=name,
        field_type=field_type,
        label=label,
        placeholder=placeholder,
        required=required,
        options=options,
        selector=selector,
    )
