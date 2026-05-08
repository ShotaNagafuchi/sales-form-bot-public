"""Tests for form submission and verification."""

from __future__ import annotations

import tempfile

import pytest

from src.submitter.screenshot import take_screenshot
from src.submitter.submit import submit_form
from src.submitter.verifier import VerifyStatus, verify_submission
from tests.conftest import fixture_url


@pytest.mark.asyncio
class TestVerifier:
    async def test_detects_success_text(self, page):
        url = fixture_url("submit_thankyou.html")
        await page.goto(url)
        # Simulate post-submit state
        await page.evaluate(
            "() => { document.body.innerHTML = '<h1>送信完了</h1><p>ありがとうございます</p>'; }"
        )
        result = await verify_submission(page, url)
        assert result.status == VerifyStatus.SUCCESS
        assert "送信完了" in result.reason or "ありがとう" in result.reason

    async def test_detects_error_text(self, page):
        url = fixture_url("submit_error.html")
        await page.goto(url)
        await page.evaluate(
            "() => { document.body.innerHTML += '<p>エラー: 必須項目を入力してください</p>'; }"
        )
        result = await verify_submission(page, url)
        assert result.status == VerifyStatus.FAILED

    async def test_uncertain_when_no_signal(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        result = await verify_submission(page, url)
        assert result.status == VerifyStatus.UNCERTAIN


@pytest.mark.asyncio
class TestScreenshot:
    async def test_takes_screenshot(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = f"{tmpdir}/test_screenshot.png"
            result = await take_screenshot(page, path)
            assert result == path
            import os
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0


@pytest.mark.asyncio
class TestSubmitForm:
    async def test_submit_success_flow(self, page):
        """Submit a form that shows a thank-you message."""
        url = fixture_url("submit_thankyou.html")
        await page.goto(url)

        # Fill required fields first
        await page.fill("#name", "テスト太郎")
        await page.fill("#email", "test@example.com")
        await page.fill("#message", "テストメッセージ")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = await submit_form(
                page,
                submit_selector="#submit-btn",
                job_id="test_001",
                screenshot_dir=tmpdir,
                humanize=False,
                dry_run=False,
            )
            assert result.verification.status == VerifyStatus.SUCCESS
            assert result.screenshot_before is not None
            assert result.screenshot_after is not None

    async def test_submit_error_flow(self, page):
        """Submit a form that shows an error message."""
        url = fixture_url("submit_error.html")
        await page.goto(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = await submit_form(
                page,
                submit_selector="#submit-btn",
                job_id="test_002",
                screenshot_dir=tmpdir,
                humanize=False,
                dry_run=False,
            )
            assert result.verification.status == VerifyStatus.FAILED
            assert result.screenshot_after is not None

    async def test_dry_run(self, page):
        """Dry run takes screenshot but does not submit."""
        url = fixture_url("submit_thankyou.html")
        await page.goto(url)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = await submit_form(
                page,
                submit_selector="#submit-btn",
                job_id="test_003",
                screenshot_dir=tmpdir,
                humanize=False,
                dry_run=True,
            )
            assert result.verification.status == VerifyStatus.UNCERTAIN
            assert "Dry run" in result.verification.reason
            assert result.screenshot_before is not None
            assert result.screenshot_after is None
