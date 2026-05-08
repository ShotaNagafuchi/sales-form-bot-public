"""DOM extraction: page → list of FormField."""

from __future__ import annotations

from playwright.async_api import Page

from src.detector.models import DetectedForm, FieldType, FormField, FormType

_INPUT_TYPE_MAP: dict[str, FieldType] = {
    "text": FieldType.TEXT,
    "email": FieldType.EMAIL,
    "tel": FieldType.TEL,
    "url": FieldType.URL,
    "number": FieldType.NUMBER,
    "date": FieldType.DATE,
    "password": FieldType.PASSWORD,
    "hidden": FieldType.HIDDEN,
    "file": FieldType.FILE,
    "checkbox": FieldType.CHECKBOX,
    "radio": FieldType.RADIO,
}


async def _resolve_label(page: Page, element_handle, field_id: str) -> str:
    """Find the label text for a field by id, aria-label, or surrounding DOM."""
    if field_id:
        label = await page.evaluate(
            """(id) => {
                const el = document.querySelector(`label[for="${id}"]`);
                return el ? el.innerText.trim() : '';
            }""",
            field_id,
        )
        if label:
            return label

    aria_label = await element_handle.get_attribute("aria-label") or ""
    if aria_label:
        return aria_label

    # Walk up to find closest wrapping label
    parent_label = await page.evaluate(
        """(el) => {
            const label = el.closest('label');
            if (label) {
                const clone = label.cloneNode(true);
                clone.querySelectorAll('input,select,textarea').forEach(c => c.remove());
                return clone.innerText.trim();
            }
            // Check preceding sibling or parent text
            const prev = el.previousElementSibling;
            if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN' || prev.tagName === 'P')) {
                return prev.innerText.trim();
            }
            return '';
        }""",
        element_handle,
    )
    return parent_label or ""


async def _extract_select_options(element_handle) -> list[str]:
    return await element_handle.evaluate(
        """(el) => Array.from(el.options)
            .filter(o => o.value !== '')
            .map(o => o.text.trim())"""
    )


async def _extract_field(page: Page, element_handle, tag: str) -> FormField | None:
    attrs = await element_handle.evaluate(
        """(el) => {
            const obj = {};
            for (const attr of el.attributes) obj[attr.name] = attr.value;
            return obj;
        }"""
    )

    input_type = attrs.get("type", "text").lower()

    # Skip submit/button/image inputs
    if input_type in ("submit", "button", "image", "reset"):
        return None

    name = attrs.get("name", "")
    field_id = attrs.get("id", "")

    if tag == "textarea":
        field_type = FieldType.TEXTAREA
    elif tag == "select":
        field_type = FieldType.SELECT
    else:
        field_type = _INPUT_TYPE_MAP.get(input_type, FieldType.UNKNOWN)

    # Skip hidden fields (usually not user-facing)
    if field_type == FieldType.HIDDEN:
        return None

    label = await _resolve_label(page, element_handle, field_id)
    placeholder = attrs.get("placeholder", "")
    required = "required" in attrs or attrs.get("aria-required") == "true"

    options: list[str] = []
    if tag == "select":
        options = await _extract_select_options(element_handle)

    # Build a robust CSS selector
    # Note: IDs starting with digits are invalid in CSS #id syntax, use [id="..."]
    if field_id:
        if field_id[0].isdigit() or not field_id.replace("-", "").replace("_", "").isalnum():
            selector = f'[id="{field_id}"]'
        else:
            selector = f"#{field_id}"
    elif name:
        selector = f'{tag}[name="{name}"]'
    else:
        selector = ""

    return FormField(
        name=name,
        field_type=field_type,
        label=label,
        placeholder=placeholder,
        required=required,
        options=options,
        selector=selector,
        attributes=attrs,
    )


def _detect_form_type(form_html: str) -> FormType:
    lower = form_html.lower()
    if "wpcf7" in lower or "wpcf7-form" in lower:
        return FormType.CONTACT_FORM_7
    if "wpforms" in lower:
        return FormType.WPFORMS
    return FormType.GENERIC


async def extract_forms(page: Page, url: str) -> list[DetectedForm]:
    """Extract all forms from the current page.

    Also detects formless inputs (inputs not inside a <form> tag),
    which is common in JS-rendered contact pages.
    """
    form_elements = await page.query_selector_all("form")

    if not form_elements:
        # Fallback: check for formless inputs (no <form> wrapper)
        return await _extract_formless_inputs(page, url)

    forms: list[DetectedForm] = []

    for idx, form_el in enumerate(form_elements):
        form_html = await form_el.evaluate("(el) => el.outerHTML")
        form_type = _detect_form_type(form_html)

        # Get form attributes
        action = await form_el.get_attribute("action") or ""
        method = (await form_el.get_attribute("method") or "POST").upper()
        form_id = await form_el.get_attribute("id") or ""
        form_class = await form_el.get_attribute("class") or ""

        form_selector = f"#{form_id}" if form_id else f"form:nth-of-type({idx + 1})"

        # Extract fields
        input_elements = await form_el.query_selector_all("input, textarea, select")
        fields: list[FormField] = []

        for el in input_elements:
            tag = await el.evaluate("(el) => el.tagName.toLowerCase()")
            field = await _extract_field(page, el, tag)
            if field is not None:
                fields.append(field)

        # Detect submit button
        submit_selector = await _find_submit_selector(form_el, form_selector)

        # Skip forms with fewer than 2 visible fields (e.g. search bars)
        visible_fields = [f for f in fields if f.field_type != FieldType.HIDDEN]
        if len(visible_fields) < 2:
            continue

        forms.append(
            DetectedForm(
                url=url,
                form_type=form_type,
                fields=fields,
                submit_selector=submit_selector,
                form_selector=form_selector,
                action=action,
                method=method,
            )
        )

    return forms


async def _extract_formless_inputs(page: Page, url: str) -> list[DetectedForm]:
    """Extract inputs that are NOT inside a <form> tag.

    Some JS-rendered pages (React, Vue) use divs with inputs instead of <form>.
    """
    input_elements = await page.query_selector_all(
        "input:not(form input):not([type='hidden']):not([type='submit']):not([type='button']), "
        "textarea:not(form textarea), "
        "select:not(form select)"
    )

    if len(input_elements) < 2:
        return []

    fields: list[FormField] = []
    for el in input_elements:
        tag = await el.evaluate("(el) => el.tagName.toLowerCase()")
        field = await _extract_field(page, el, tag)
        if field is not None:
            fields.append(field)

    visible_fields = [f for f in fields if f.field_type != FieldType.HIDDEN]
    if len(visible_fields) < 2:
        return []

    # Try to find a submit button anywhere on the page
    submit_selector = ""
    for sel in [
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("送信")',
        'button:has-text("Submit")',
        'button:has-text("確認")',
        "button.submit",
    ]:
        btn = await page.query_selector(sel)
        if btn:
            submit_selector = sel
            break

    return [
        DetectedForm(
            url=url,
            form_type=FormType.GENERIC,
            fields=fields,
            submit_selector=submit_selector,
            form_selector="body",
            action="",
            method="POST",
        )
    ]


async def _find_submit_selector(form_el, form_selector: str) -> str:
    """Find the submit button within a form."""
    # Try input[type=submit]
    submit_btn = await form_el.query_selector('input[type="submit"]')
    if submit_btn:
        btn_id = await submit_btn.get_attribute("id")
        if btn_id:
            return f"#{btn_id}"
        return f'{form_selector} input[type="submit"]'

    # Try button[type=submit]
    submit_btn = await form_el.query_selector('button[type="submit"]')
    if submit_btn:
        btn_id = await submit_btn.get_attribute("id")
        if btn_id:
            return f"#{btn_id}"
        return f'{form_selector} button[type="submit"]'

    # Try any button
    submit_btn = await form_el.query_selector("button")
    if submit_btn:
        return f"{form_selector} button"

    return ""
