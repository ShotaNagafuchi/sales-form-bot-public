"""Compare form filling strategies on a sample of companies.

Usage:
    python3 scripts/compare_strategies.py --csv data/companies.csv --sample 30 --seed 100

Outputs a comparison CSV showing each strategy's performance per URL.
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

from playwright.async_api import async_playwright

from src.config import BrowserConfig
from src.detector.extractor import extract_forms
from src.detector.finder import _find_contact_links, _navigate_and_extract
from src.detector.parsers.wordpress import parse_cf7, parse_wpforms
from src.filler.engine import fill_form
from src.mapper.strategies import (
    ALL_STRATEGIES,
    map_strategy_a,
    map_strategy_b,
    map_strategy_c,
    map_strategy_d,
    map_strategy_hybrid,
)
from src.mapper.validator import validate_mappings
from src.profile import load_profile

logger = logging.getLogger(__name__)

STRATEGY_FUNCS = {
    "rule_based": map_strategy_a,
    "name_attr": map_strategy_b,
    "semantic": map_strategy_c,
    "sequential": map_strategy_d,
    "hybrid": map_strategy_hybrid,
}

DEFAULT_PROFILE = load_profile()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compare mapping strategies")
    p.add_argument("--csv", required=True, help="Company CSV file")
    p.add_argument("--sample", "-n", type=int, default=30)
    p.add_argument("--seed", type=int, default=100)
    p.add_argument("--headed", action="store_true")
    return p.parse_args()


def load_targets(csv_path: str, sample: int, seed: int) -> list[dict]:
    targets = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("URL", "").strip()
            if url:
                targets.append({
                    "code": row.get("コード", ""),
                    "name": row.get("銘柄名", ""),
                    "url": url,
                    "industry": row.get("33業種区分", ""),
                })
    random.seed(seed)
    return random.sample(targets, min(sample, len(targets)))


async def detect_form_on_url(page, url: str):
    """Navigate and detect form, returns (form, actual_url) or (None, url)."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if response is None or response.status >= 400:
            return None, url
        await page.wait_for_timeout(1500)
    except Exception:
        return None, url

    # Try CMS parsers first
    forms = await parse_cf7(page, url)
    if not forms:
        forms = await parse_wpforms(page, url)
    if not forms:
        forms = await extract_forms(page, url)

    if forms:
        return forms[0], page.url

    # Try contact links
    try:
        contact_links = await _find_contact_links(page, url)
    except Exception:
        contact_links = []

    for link in contact_links[:5]:
        try:
            resp = await page.goto(link, wait_until="domcontentloaded", timeout=20_000)
            if resp and resp.status < 400:
                await page.wait_for_timeout(1500)
                forms = await parse_cf7(page, link)
                if not forms:
                    forms = await parse_wpforms(page, link)
                if not forms:
                    forms = await extract_forms(page, link)
                if forms:
                    return forms[0], page.url
        except Exception:
            continue

    # Probe common paths as last resort
    from src.detector.finder import _CONTACT_PATHS
    base = url.rstrip("/")
    for path in _CONTACT_PATHS[:10]:
        try:
            candidate = base + path
            resp = await page.goto(candidate, wait_until="domcontentloaded", timeout=15_000)
            if resp and resp.status < 400:
                await page.wait_for_timeout(1000)
                forms = await extract_forms(page, candidate)
                if forms:
                    return forms[0], page.url
        except Exception:
            continue

    return None, url


async def test_strategy(page, form, strategy_name: str, profile: dict) -> dict:
    """Test a single strategy on a detected form. Returns metrics."""
    mapper = STRATEGY_FUNCS[strategy_name]
    mapping_result = mapper(form, profile)
    validation = validate_mappings(mapping_result, form, confidence_threshold=0.5)

    # Try filling (without submit)
    filled_count = 0
    error_count = 0

    if validation.valid_mappings:
        fill_result = await fill_form(page, validation.valid_mappings, humanize=False)
        filled_count = len(fill_result.filled)
        error_count = len(fill_result.errors)

    return {
        "strategy": strategy_name,
        "fields_total": len(form.fields),
        "fields_mapped": len(mapping_result.mappings) - len(mapping_result.unmapped_fields),
        "fields_validated": len(validation.valid_mappings),
        "fields_filled": filled_count,
        "fields_errors": error_count,
        "ready_to_fill": validation.ready_to_fill,
        "fill_rate": filled_count / len(form.fields) if form.fields else 0,
    }


async def run(args: argparse.Namespace) -> None:
    targets = load_targets(args.csv, args.sample, args.seed)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(f"results/compare_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*70}")
    print(f"  Strategy Comparison — {len(targets)} companies")
    print(f"  Strategies: {', '.join(s.name for s in ALL_STRATEGIES)}")
    print(f"  Output: {output_dir}/")
    print(f"{'='*70}\n")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=not args.headed)

    rows: list[dict] = []
    strategy_totals: dict[str, dict] = {s.name: {"filled": 0, "total": 0, "forms_found": 0} for s in ALL_STRATEGIES}

    for i, target in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {target['name']}", end=" ... ", flush=True)

        context = await browser.new_context(locale="ja-JP")
        page = await context.new_page()

        form, actual_url = await detect_form_on_url(page, target["url"])

        if form is None:
            print("NO FORM")
            for s in ALL_STRATEGIES:
                rows.append({
                    "code": target["code"],
                    "name": target["name"],
                    "url": target["url"],
                    "industry": target["industry"],
                    "form_found": False,
                    "form_url": "",
                    "strategy": s.name,
                    "fields_total": 0,
                    "fields_mapped": 0,
                    "fields_validated": 0,
                    "fields_filled": 0,
                    "fields_errors": 0,
                    "ready_to_fill": False,
                    "fill_rate": 0,
                })
            await context.close()
            continue

        print(f"FORM ({len(form.fields)} fields) ", end="")

        # Test each strategy
        strategy_results = []
        for s in ALL_STRATEGIES:
            # Reload page for each strategy to get clean state
            try:
                await page.goto(actual_url, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(500)
            except Exception:
                pass

            result = await test_strategy(page, form, s.name, DEFAULT_PROFILE)
            strategy_results.append(result)
            strategy_totals[s.name]["filled"] += result["fields_filled"]
            strategy_totals[s.name]["total"] += result["fields_total"]
            strategy_totals[s.name]["forms_found"] += 1

            rows.append({
                "code": target["code"],
                "name": target["name"],
                "url": target["url"],
                "industry": target["industry"],
                "form_found": True,
                "form_url": actual_url,
                **result,
            })

        # Print compact results
        results_str = " | ".join(
            f"{r['strategy'][:4]}:{r['fields_filled']}/{r['fields_total']}"
            for r in strategy_results
        )
        print(results_str)

        await context.close()

    await browser.close()
    await pw.stop()

    # Write detailed CSV
    csv_path = output_dir / "comparison.csv"
    fieldnames = ["code", "name", "url", "industry", "form_found", "form_url",
                  "strategy", "fields_total", "fields_mapped", "fields_validated",
                  "fields_filled", "fields_errors", "ready_to_fill", "fill_rate"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary
    print(f"\n{'='*70}")
    print(f"  STRATEGY COMPARISON RESULTS")
    print(f"{'='*70}")
    print(f"  {'Strategy':<15} {'Forms Found':<12} {'Fill Rate':<12} {'Avg Fill/Form'}")
    print(f"  {'-'*55}")

    for s in ALL_STRATEGIES:
        t = strategy_totals[s.name]
        forms_found = t["forms_found"]
        if t["total"] > 0:
            fill_rate = t["filled"] / t["total"] * 100
            avg_fill = t["filled"] / forms_found if forms_found else 0
        else:
            fill_rate = 0
            avg_fill = 0
        print(f"  {s.name:<15} {forms_found:<12} {fill_rate:>5.1f}%      {avg_fill:.1f}")

    print(f"\n  Detailed CSV: {csv_path}")
    print(f"{'='*70}")


def main():
    logging.basicConfig(level=logging.WARNING)
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
