"""End-to-end pipeline test: job JSON → detect → map → fill → submit → result JSON."""

from __future__ import annotations

import json
import tempfile

import pytest

from src.config import Config, BrowserConfig, QueueConfig
from src.queue.consumer import load_pending_jobs, process_job, save_result
from src.queue.models import FormJob, JobStatus
from tests.conftest import fixture_url


def _make_job(url: str, dry_run: bool = True) -> FormJob:
    return FormJob.model_validate({
        "job_id": "e2e_test_001",
        "url": url,
        "profile": {
            "company_name": "Acme Corporation",
            "name": "Taro Yamada",
            "email": "taro@example.com",
            "phone": "0312345678",
            "department": "代表",
            "message": "テストメッセージです。",
        },
        "options": {
            "dry_run": dry_run,
            "screenshot": True,
        },
    })


@pytest.mark.asyncio
class TestPipeline:
    async def test_e2e_dry_run(self):
        """Full pipeline dry run on a local form fixture."""
        url = fixture_url("submit_thankyou.html")
        job = _make_job(url, dry_run=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                browser=BrowserConfig(headless=True),
                queue=QueueConfig(completed_dir=f"{tmpdir}/completed"),
                screenshot_dir=f"{tmpdir}/screenshots",
            )
            result = await process_job(job, config)

            assert result.job_id == "e2e_test_001"
            assert result.fields_filled > 0
            assert result.screenshot_before is not None

    async def test_e2e_generic_form_fills(self):
        """Pipeline fills generic form including select fallback."""
        url = fixture_url("generic_contact.html")
        job = _make_job(url, dry_run=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                browser=BrowserConfig(headless=True),
                queue=QueueConfig(completed_dir=f"{tmpdir}/completed"),
                screenshot_dir=f"{tmpdir}/screenshots",
            )
            result = await process_job(job, config)
            # Select fields now get fallback options, so form should be fillable
            assert result.fields_filled > 0

    async def test_e2e_submit_success(self):
        """Full pipeline with actual submit on thank-you fixture."""
        url = fixture_url("submit_thankyou.html")
        job = _make_job(url, dry_run=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                browser=BrowserConfig(headless=True),
                queue=QueueConfig(completed_dir=f"{tmpdir}/completed"),
                screenshot_dir=f"{tmpdir}/screenshots",
            )
            result = await process_job(job, config)

            assert result.job_id == "e2e_test_001"
            assert result.status == JobStatus.SUCCESS
            assert result.fields_filled >= 3
            assert result.screenshot_after is not None

    async def test_e2e_form_not_found(self):
        """Pipeline returns FORM_NOT_FOUND for a page without forms."""
        # Use a blank page
        job = _make_job("about:blank", dry_run=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                browser=BrowserConfig(headless=True),
                queue=QueueConfig(completed_dir=f"{tmpdir}/completed"),
                screenshot_dir=f"{tmpdir}/screenshots",
            )
            result = await process_job(job, config)
            assert result.status == JobStatus.FORM_NOT_FOUND


class TestQueueIO:
    def test_load_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            job_data = {
                "job_id": "io_test_001",
                "url": "https://example.com/contact",
                "profile": {
                    "company_name": "Test Co",
                    "name": "テスト太郎",
                    "email": "test@example.com",
                },
            }
            job_file = f"{tmpdir}/io_test_001.json"
            with open(job_file, "w", encoding="utf-8") as f:
                json.dump(job_data, f, ensure_ascii=False)

            jobs = load_pending_jobs(tmpdir)
            assert len(jobs) == 1
            assert jobs[0].job_id == "io_test_001"
            assert jobs[0].profile.company_name == "Test Co"

    def test_save_result(self):
        from src.queue.models import JobResult, JobStatus

        result = JobResult(
            job_id="save_test_001",
            status=JobStatus.SUCCESS,
            url="https://example.com/contact",
            fields_filled=5,
            fields_total=7,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_result(result, tmpdir)
            assert path.exists()
            saved = json.loads(path.read_text())
            assert saved["job_id"] == "save_test_001"
            assert saved["status"] == "success"
