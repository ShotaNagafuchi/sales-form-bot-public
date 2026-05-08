"""Submit form and verify the result."""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from src.filler.humanizer import human_click, scroll_to_element
from src.submitter.screenshot import take_screenshot
from src.submitter.verifier import VerifyResult, VerifyStatus, verify_submission


@dataclass(frozen=True)
class SubmitResult:
    verification: VerifyResult
    screenshot_before: str | None
    screenshot_after: str | None


async def submit_form(
    page: Page,
    submit_selector: str,
    job_id: str,
    screenshot_dir: str = "results/screenshots",
    humanize: bool = True,
    dry_run: bool = False,
) -> SubmitResult:
    """Click submit, wait for navigation/response, and verify success.

    Args:
        page: Playwright page with the filled form.
        submit_selector: CSS selector for the submit button.
        job_id: Job ID for naming screenshots.
        screenshot_dir: Directory for screenshot storage.
        humanize: Use human-like click behavior.
        dry_run: If True, take screenshots but do not actually submit.
    """
    # Screenshot before submission
    before_path = f"{screenshot_dir}/{job_id}_before.png"
    await take_screenshot(page, before_path)

    if dry_run:
        return SubmitResult(
            verification=VerifyResult(
                status=VerifyStatus.UNCERTAIN,
                reason="Dry run — form was not submitted",
                url_after=page.url,
            ),
            screenshot_before=before_path,
            screenshot_after=None,
        )

    url_before = page.url

    # Scroll to and click submit
    await scroll_to_element(page, submit_selector)

    # Click submit — some forms navigate (load event), others stay on the same
    # page (SPA / AJAX). Try to wait for navigation but fall back gracefully.
    if humanize:
        await human_click(page, submit_selector)
    else:
        await page.click(submit_selector)

    # Wait for any navigation or DOM update to settle
    try:
        await page.wait_for_load_state("networkidle", timeout=5_000)
    except Exception:
        pass
    await page.wait_for_timeout(2000)

    # Verify submission result
    verification = await verify_submission(page, url_before)

    # Screenshot after submission
    after_path = f"{screenshot_dir}/{job_id}_after.png"
    await take_screenshot(page, after_path)

    return SubmitResult(
        verification=verification,
        screenshot_before=before_path,
        screenshot_after=after_path,
    )


async def find_and_click_submit(
    page: Page,
    submit_selector: str,
) -> bool:
    """Find and click the submit button. Returns False if not found."""
    element = await page.query_selector(submit_selector)
    if element is None:
        # Fallback: try common submit selectors
        for fallback in [
            'input[type="submit"]',
            'button[type="submit"]',
            "button:has-text('送信')",
            "button:has-text('Submit')",
        ]:
            element = await page.query_selector(fallback)
            if element:
                break

    if element is None:
        return False

    await element.click()
    return True
