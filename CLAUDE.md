# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Playwright + LLM-based bot that auto-detects, fills, and submits contact forms for sales outreach. Receives jobs as JSON from the `sales-ai` sibling repo, processes forms asynchronously, and reports results back.

## Architecture

```
Queue Consumer → Form Detector (Playwright) → Field Mapper (LLM) → Form Filler (Playwright) → Submitter + Verifier → Result Reporter
```

- **Queue**: JSON file-based (`queue/pending/` → `results/completed/`), future Redis migration planned
- **LLM**: Claude API (Haiku) for semantic field mapping (e.g. "御社名" → company_name)
- **CAPTCHA**: Multi-strategy (Turnstile auto-wait, reCAPTCHA v2 via 2Captcha API, skip on failure)
- **Humanization**: Typing delay 50-150ms/char, inter-field delay 500-2000ms, cursor jitter, natural scroll

## Tech Stack

- Python 3.11+, Playwright (async), Pydantic v2, Claude API (Haiku), 2Captcha, Docker

## Commands

```bash
# Setup
pip install -r requirements.txt
playwright install chromium

# Run
python -m src.queue.consumer              # Process pending jobs
python -m src.queue.consumer --dry-run    # Preview without submitting

# Test
pytest tests/
pytest tests/test_detector.py -k "test_cf7"  # Single test

# Docker
docker compose up                         # Full environment with headless Chrome

# Lint
ruff check src/ tests/
mypy src/
```

## Integration with sales-ai

- Input: `sales-ai` writes job JSON files to `queue/pending/`
- Output: This bot writes result JSON to `results/completed/`
- Job schema: `{job_id, url, profile: {company_name, name, email, phone, message}, options: {captcha_solve, max_retries, screenshot, dry_run}}`
- Result schema: `{job_id, status: success|failed|captcha_blocked|form_not_found|skipped, fields_filled, screenshot_before, screenshot_after, error}`

## Key Design Decisions

- Japanese contact forms prioritized (Contact Form 7, WPForms are most common)
- Form parsers use factory pattern: generic, google_form, wordpress-specific
- Fields with confidence below threshold trigger human review instead of blind submission
- Daily submission cap (10/day) for legal compliance
- Screenshots saved before and after submission for verification
