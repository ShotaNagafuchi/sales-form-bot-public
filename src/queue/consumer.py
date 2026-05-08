"""Queue consumer: read job JSON files, process forms, write results."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from src.config import Config
from src.detector.extractor import extract_forms
from src.detector.finder import (
    _CONTACT_PATHS,
    _extract_iframe_forms,
    _find_contact_links,
    _find_form_sub_links,
    _navigate_and_extract,
)
from src.detector.llm_finder import FormURLCache, find_form_url_with_llm
from src.detector.sitemap import find_contact_urls_from_sitemap
from src.detector.parsers.wordpress import parse_cf7, parse_wpforms
from src.filler.engine import fill_form
from src.mapper.strategies import map_strategy_hybrid
from src.mapper.validator import validate_mappings
from src.queue.models import FormJob, JobResult, JobStatus
from src.submitter.submit import submit_form
from src.submitter.verifier import VerifyStatus

logger = logging.getLogger(__name__)


async def _navigate_and_extract_patient(page, url: str):
    """Navigate with longer waits for JS-heavy sites (used for cached/known URLs)."""
    try:
        response = await page.goto(url, wait_until="load", timeout=30_000)
        if response is None or response.status >= 400:
            return []
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        await page.wait_for_timeout(5000)
        from src.detector.extractor import extract_forms
        forms = await extract_forms(page, url)
        if forms:
            return forms
        from src.detector.finder import _extract_iframe_forms
        return await _extract_iframe_forms(page, url)
    except Exception:
        return []


async def _detect_forms_on_page(page, url: str):
    """Try CMS-specific parsers first, then generic, then iframes."""
    forms = await parse_cf7(page, url)
    if not forms:
        forms = await parse_wpforms(page, url)
    if not forms:
        forms = await extract_forms(page, url)
    if not forms:
        forms = await _extract_iframe_forms(page, url)
    return forms


async def process_job(job: FormJob, config: Config) -> JobResult:
    """Process a single form submission job end-to-end."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=config.browser.headless)
    context = await browser.new_context(locale="ja-JP", user_agent=config.browser.user_agent)
    page = await context.new_page()

    try:
        # 1. Navigate to URL
        response = await page.goto(
            job.url, wait_until="domcontentloaded", timeout=config.browser.timeout_ms
        )
        if response is None or response.status >= 400:
            return _result(job, JobStatus.FORM_NOT_FOUND, error=f"HTTP {response.status if response else 'no response'}")

        await page.wait_for_timeout(1500)

        # 2. Detect forms — multi-stage discovery
        forms = []

        # Check cache first (LLM-discovered URLs from previous runs)
        cache = FormURLCache()
        cached_url = cache.get(job.url)
        if cached_url:
            # Cached URLs are known to have forms — use longer wait for JS rendering
            forms = await _navigate_and_extract_patient(page, cached_url)
            if forms:
                logger.info("Form found via cache: %s", cached_url)

        if not forms:
            forms = await _detect_forms_on_page(page, job.url)

        contact_links = []
        if not forms:
            # 2a. Follow contact links found on the page
            contact_links = await _find_contact_links(page, job.url)
            for link in contact_links[:5]:
                forms = await _navigate_and_extract(page, link)
                if forms:
                    break

        if not forms and contact_links:
            # 2b. Contact page had no form — check sub-links (category→form pattern)
            for link in contact_links[:2]:
                try:
                    await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
                    await page.wait_for_timeout(1500)
                    sub_links = await _find_form_sub_links(page)
                    for sub in sub_links[:3]:
                        forms = await _navigate_and_extract(page, sub)
                        if forms:
                            break
                    if forms:
                        break
                except Exception:
                    continue

        if not forms:
            # 2c. Check sitemap.xml for contact URLs
            sitemap_urls = await find_contact_urls_from_sitemap(page, job.url)
            for surl in sitemap_urls[:5]:
                forms = await _navigate_and_extract(page, surl)
                if forms:
                    break

        if not forms:
            # 2d. Probe common paths as last resort
            base = job.url.rstrip("/")
            for path in _CONTACT_PATHS[:10]:
                forms = await _navigate_and_extract(page, base + path)
                if forms:
                    break

        if not forms:
            # 2e. LLM analysis — last resort, expensive but finds external forms
            if config.llm.api_key:
                # Navigate to the most promising contact page for LLM analysis
                best_contact_page = contact_links[0] if contact_links else job.url
                try:
                    await page.goto(best_contact_page, wait_until="domcontentloaded", timeout=15_000)
                    await page.wait_for_timeout(2000)
                    llm_url = await find_form_url_with_llm(page, best_contact_page, config.llm)
                    if llm_url and llm_url != best_contact_page:
                        forms = await _navigate_and_extract(page, llm_url)
                        if forms:
                            # Cache for next time
                            cache.set(job.url, llm_url)
                            logger.info("Form found via LLM: %s (cached)", llm_url)
                except Exception:
                    pass

        if not forms:
            return _result(job, JobStatus.FORM_NOT_FOUND, error="No contact form found")

        form = forms[0]  # Use the first detected form

        # 2f. Ensure we're on the page where the form was found
        if page.url != form.url:
            try:
                await page.goto(form.url, wait_until="load", timeout=30_000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                await page.wait_for_timeout(2000)
            except Exception:
                pass

        # 3. Map fields to profile data (hybrid: rule-based + sequential fallback)
        profile_dict = job.profile.model_dump()
        mapping_result = map_strategy_hybrid(form, profile_dict)

        # 4. Validate mappings (use lower threshold, skip readiness check to fill what we can)
        validation = validate_mappings(mapping_result, form, confidence_threshold=0.5)
        if not validation.valid_mappings:
            warnings = "; ".join(validation.warnings)
            return _result(
                job, JobStatus.SKIPPED,
                fields_total=len(form.fields),
                error=f"Missing required fields: {warnings}",
            )

        # 5. Fill the form
        fill_result = await fill_form(
            page, validation.valid_mappings,
            humanize=not job.options.dry_run,
        )

        # 6. Submit
        submit_result = await submit_form(
            page,
            submit_selector=form.submit_selector,
            job_id=job.job_id,
            screenshot_dir=config.screenshot_dir,
            humanize=not job.options.dry_run,
            dry_run=job.options.dry_run,
        )

        # 7. Map verification status to job status
        status_map = {
            VerifyStatus.SUCCESS: JobStatus.SUCCESS,
            VerifyStatus.FAILED: JobStatus.FAILED,
            VerifyStatus.UNCERTAIN: JobStatus.FAILED,
        }
        job_status = status_map.get(submit_result.verification.status, JobStatus.FAILED)

        return _result(
            job,
            job_status,
            fields_filled=len(fill_result.filled),
            fields_total=len(form.fields),
            fields_skipped=fill_result.skipped + fill_result.errors,
            screenshot_before=submit_result.screenshot_before,
            screenshot_after=submit_result.screenshot_after,
            error=submit_result.verification.reason if job_status != JobStatus.SUCCESS else None,
        )

    except Exception as e:
        logger.exception("Job %s failed", job.job_id)
        return _result(job, JobStatus.FAILED, error=str(e))

    finally:
        await context.close()
        await browser.close()
        await pw.stop()


def _result(
    job: FormJob,
    status: JobStatus,
    fields_filled: int = 0,
    fields_total: int = 0,
    fields_skipped: list[str] | None = None,
    screenshot_before: str | None = None,
    screenshot_after: str | None = None,
    error: str | None = None,
) -> JobResult:
    return JobResult(
        job_id=job.job_id,
        status=status,
        url=job.url,
        fields_filled=fields_filled,
        fields_total=fields_total,
        fields_skipped=fields_skipped or [],
        screenshot_before=screenshot_before,
        screenshot_after=screenshot_after,
        error=error,
    )


def load_pending_jobs(pending_dir: str) -> list[FormJob]:
    """Load all pending job JSON files from the queue directory."""
    jobs: list[FormJob] = []
    pending_path = Path(pending_dir)
    if not pending_path.exists():
        return jobs

    for f in sorted(pending_path.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            jobs.append(FormJob.model_validate(data))
        except Exception as e:
            logger.warning("Failed to parse job file %s: %s", f, e)
    return jobs


def save_result(result: JobResult, completed_dir: str) -> Path:
    """Write result JSON to the completed directory."""
    completed_path = Path(completed_dir)
    completed_path.mkdir(parents=True, exist_ok=True)
    output = completed_path / f"{result.job_id}.json"
    output.write_text(
        result.model_dump_json(indent=2),
        encoding="utf-8",
    )
    return output


def move_to_completed(job_file: Path, completed_dir: str) -> None:
    """Remove the pending job file after processing."""
    job_file.unlink(missing_ok=True)


async def run_queue(config: Config | None = None) -> list[JobResult]:
    """Process all pending jobs in the queue."""
    cfg = config or Config()
    jobs = load_pending_jobs(cfg.queue.pending_dir)
    if not jobs:
        logger.info("No pending jobs")
        return []

    logger.info("Processing %d jobs", len(jobs))
    results: list[JobResult] = []

    for job in jobs:
        logger.info("Processing job %s: %s", job.job_id, job.url)
        result = await process_job(job, cfg)
        save_result(result, cfg.queue.completed_dir)

        # Remove from pending
        job_file = Path(cfg.queue.pending_dir) / f"{job.job_id}.json"
        move_to_completed(job_file, cfg.queue.completed_dir)

        results.append(result)
        logger.info("Job %s: %s", job.job_id, result.status.value)

    return results


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dry_run = "--dry-run" in sys.argv
    cfg = Config()

    if dry_run:
        logger.info("DRY RUN mode — forms will not be submitted")

    jobs = load_pending_jobs(cfg.queue.pending_dir)
    if not jobs:
        logger.info("No pending jobs in %s", cfg.queue.pending_dir)
        return

    for job in jobs:
        if dry_run:
            job = job.model_copy(
                update={"options": job.options.model_copy(update={"dry_run": True})}
            )
        result = await process_job(job, cfg)
        save_result(result, cfg.queue.completed_dir)
        logger.info("Job %s: %s", result.job_id, result.status.value)


if __name__ == "__main__":
    asyncio.run(main())
