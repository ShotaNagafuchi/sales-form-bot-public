"""Verify form submission success/failure by inspecting the page after submit."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from playwright.async_api import Page

# Japanese and English success indicators
_SUCCESS_TEXTS = [
    "ありがとう",
    "送信完了",
    "送信されました",
    "送信いたしました",
    "受け付けました",
    "お問い合わせを受け付け",
    "thank you",
    "thanks for",
    "successfully sent",
    "message sent",
    "submission received",
    "we have received",
    "完了しました",
    "送信が完了",
]

_SUCCESS_URL_PATTERNS = [
    "/thanks",
    "/thank-you",
    "/thankyou",
    "/complete",
    "/done",
    "/success",
    "/sent",
    "/confirmation",
]

_ERROR_TEXTS = [
    "エラー",
    "入力してください",
    "必須項目",
    "正しく入力",
    "is required",
    "please fill",
    "invalid",
    "error",
    "validation failed",
]


class VerifyStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class VerifyResult:
    status: VerifyStatus
    reason: str
    url_after: str


async def verify_submission(page: Page, url_before: str) -> VerifyResult:
    """Check whether form submission succeeded by analyzing the page state.

    Checks in order:
    1. URL change to a known success path
    2. Success text appearing in page body
    3. Validation error text appearing (= failure)
    4. URL changed but no clear signal (= uncertain)
    """
    url_after = page.url

    # 1. Check URL path for success patterns
    url_lower = url_after.lower()
    for pattern in _SUCCESS_URL_PATTERNS:
        if pattern in url_lower and url_after != url_before:
            return VerifyResult(
                status=VerifyStatus.SUCCESS,
                reason=f"Redirected to success URL: {url_after}",
                url_after=url_after,
            )

    # 2. Check page body for success text
    body_text = await _get_visible_text(page)
    body_lower = body_text.lower()

    for text in _SUCCESS_TEXTS:
        if text.lower() in body_lower:
            return VerifyResult(
                status=VerifyStatus.SUCCESS,
                reason=f"Success text found: '{text}'",
                url_after=url_after,
            )

    # 3. Check for validation errors
    for text in _ERROR_TEXTS:
        if text.lower() in body_lower:
            return VerifyResult(
                status=VerifyStatus.FAILED,
                reason=f"Error text found: '{text}'",
                url_after=url_after,
            )

    # 4. URL changed but no clear signal
    if url_after != url_before:
        return VerifyResult(
            status=VerifyStatus.UNCERTAIN,
            reason=f"URL changed to {url_after} but no success/error text detected",
            url_after=url_after,
        )

    return VerifyResult(
        status=VerifyStatus.UNCERTAIN,
        reason="No URL change and no success/error text detected",
        url_after=url_after,
    )


async def _get_visible_text(page: Page) -> str:
    """Get the visible text content of the page body."""
    return await page.evaluate("() => document.body?.innerText || ''")
