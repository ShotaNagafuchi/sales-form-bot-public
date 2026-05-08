"""Benchmark form detection + filling on company URLs.

Usage:
    # Random sample 10 companies from CSV, dry run
    python3 scripts/try_forms.py --csv data/companies.csv --sample 10

    # Specific URLs
    python3 scripts/try_forms.py https://example.co.jp https://example2.co.jp

    # From a text file (one URL per line)
    python3 scripts/try_forms.py --file urls.txt

    # Actually submit (use with caution!)
    python3 scripts/try_forms.py --submit --csv data/companies.csv --sample 3

    # Show browser window
    python3 scripts/try_forms.py --headed --csv data/companies.csv --sample 5

Results are saved to results/try_<timestamp>/results.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import BrowserConfig, Config, QueueConfig
from src.profile import load_profile
from src.queue.consumer import process_job
from src.queue.models import FormJob

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark form bot")
    p.add_argument("urls", nargs="*", help="URLs to try")
    p.add_argument("--file", "-f", help="Text file with one URL per line")
    p.add_argument("--csv", help="Company CSV (columns: コード,銘柄名,URL,...)")
    p.add_argument("--sample", "-n", type=int, default=0, help="Random sample N from CSV")
    p.add_argument("--profile", "-p", help="Profile JSON file")
    p.add_argument("--submit", action="store_true", help="Actually submit (default: dry run)")
    p.add_argument("--headed", action="store_true", help="Show browser window")
    p.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    return p.parse_args()


def load_targets(args: argparse.Namespace) -> list[dict]:
    """Load targets as list of {code, name, url, industry}."""
    targets: list[dict] = []

    if args.csv:
        with open(args.csv, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("URL", "").strip()
                if url:
                    targets.append({
                        "code": row.get("コード", ""),
                        "name": row.get("銘柄名", ""),
                        "url": url,
                        "industry": row.get("33業種区分", ""),
                    })

        if args.sample > 0:
            random.seed(args.seed)
            targets = random.sample(targets, min(args.sample, len(targets)))

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    targets.append({"code": "", "name": "", "url": line, "industry": ""})

    for url in args.urls:
        targets.append({"code": "", "name": "", "url": url, "industry": ""})

    return targets


def _load_profile(path: str | None) -> dict[str, str]:
    return load_profile(path)


async def run(args: argparse.Namespace) -> None:
    targets = load_targets(args)
    if not targets:
        print("No targets. Use --csv, --file, or pass URLs directly.")
        sys.exit(1)

    profile = load_profile(args.profile)
    dry_run = not args.submit
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = f"results/try_{timestamp}"

    config = Config(
        browser=BrowserConfig(headless=not args.headed),
        queue=QueueConfig(completed_dir=f"{output_dir}/completed"),
        screenshot_dir=f"{output_dir}/screenshots",
    )

    # Prepare results CSV
    results_csv = Path(output_dir) / "results.csv"
    results_csv.parent.mkdir(parents=True, exist_ok=True)

    mode = "DRY RUN" if dry_run else "LIVE SUBMIT"
    print(f"\n{'='*60}")
    print(f"  Form Bot Benchmark — {mode}")
    print(f"  {len(targets)} target(s)")
    print(f"  Results CSV: {results_csv}")
    print(f"  Screenshots: {config.screenshot_dir}/")
    print(f"{'='*60}\n")

    rows: list[dict] = []

    for i, target in enumerate(targets, 1):
        job_id = f"try_{timestamp}_{i:03d}"
        print(f"[{i}/{len(targets)}] {target['name'] or target['url']}", end=" ... ", flush=True)

        job = FormJob.model_validate({
            "job_id": job_id,
            "url": target["url"],
            "profile": profile,
            "options": {"dry_run": dry_run, "screenshot": True},
        })

        result = await process_job(job, config)

        status_icon = {
            "success": "OK", "failed": "NG", "skipped": "SKIP",
            "form_not_found": "NO FORM", "captcha_blocked": "CAPTCHA",
        }.get(result.status.value, "??")
        print(f"[{status_icon}] {result.fields_filled}/{result.fields_total}")

        rows.append({
            "code": target["code"],
            "name": target["name"],
            "url": target["url"],
            "industry": target["industry"],
            "status": result.status.value,
            "fields_filled": result.fields_filled,
            "fields_total": result.fields_total,
            "fields_skipped": ";".join(result.fields_skipped),
            "error": result.error or "",
            "screenshot_before": result.screenshot_before or "",
            "screenshot_after": result.screenshot_after or "",
        })

    # Write results CSV
    fieldnames = ["code", "name", "url", "industry", "status",
                  "fields_filled", "fields_total", "fields_skipped",
                  "error", "screenshot_before", "screenshot_after"]
    with open(results_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    total = len(rows)
    filled = sum(1 for r in rows if int(r["fields_filled"]) > 0)
    no_form = sum(1 for r in rows if r["status"] == "form_not_found")
    skipped = sum(1 for r in rows if r["status"] == "skipped")

    print(f"\n{'='*60}")
    print(f"  Results: {results_csv}")
    print(f"  Form found & filled: {filled}/{total} ({filled/total*100:.0f}%)")
    print(f"  No form found:       {no_form}/{total}")
    print(f"  Skipped:             {skipped}/{total}")
    print(f"{'='*60}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
