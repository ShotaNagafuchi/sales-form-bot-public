"""Auto-build form URL cache by deep-crawling NO FORM companies.

For each NO FORM company:
1. Visit top page → find contact links (including buttons/onclick)
2. Follow contact links → check for forms
3. On contact page: follow sub-links (category → form pattern)
4. Check iframes for external form services
5. Try sitemap.xml
6. Try extended path probes
7. If form found, add to cache

Usage:
    python3 scripts/build_cache.py results/try_XXXXXXX/results.csv
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from src.detector.extractor import extract_forms
from src.detector.finder import (
    _AD_IFRAME_PATTERNS,
    _CONTACT_PATHS,
    _FORM_IFRAME_PATTERNS,
    _LINK_KEYWORDS,
)
from src.detector.sitemap import find_contact_urls_from_sitemap

CACHE_PATH = "data/form_url_cache.json"


def load_cache() -> dict[str, str]:
    try:
        return json.loads(Path(CACHE_PATH).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache: dict[str, str]) -> None:
    Path(CACHE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(CACHE_PATH).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def domain(url: str) -> str:
    return urlparse(url).netloc


async def find_contact_links_broad(page) -> list[dict]:
    """Find contact links — broader than finder.py, includes buttons and JS."""
    return await page.evaluate(
        """(keywords) => {
            const results = [];
            const seen = new Set();

            // <a> tags
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                const text = (a.innerText || '').toLowerCase();
                if (!href.startsWith('http') || seen.has(href)) continue;
                for (const kw of keywords) {
                    if (text.includes(kw) || href.toLowerCase().includes(kw)) {
                        results.push({href, text: (a.innerText||'').trim().substring(0,50), source: 'a'});
                        seen.add(href);
                        break;
                    }
                }
            }

            // onclick, data-href
            for (const el of document.querySelectorAll('[onclick], [data-href]')) {
                const onclick = el.getAttribute('onclick') || '';
                const dataHref = el.getAttribute('data-href') || '';
                const text = (el.innerText || '').toLowerCase();
                const m = (onclick + dataHref).match(/['"]?(https?:\\/\\/[^'"\\s]+)['"]?/);
                if (m && !seen.has(m[1])) {
                    for (const kw of keywords) {
                        if (text.includes(kw) || m[1].toLowerCase().includes(kw)) {
                            results.push({href: m[1], text: (el.innerText||'').trim().substring(0,50), source: 'onclick'});
                            seen.add(m[1]);
                            break;
                        }
                    }
                }
            }

            return results;
        }""",
        _LINK_KEYWORDS,
    )


async def check_page_for_form(page, url: str) -> tuple[bool, int]:
    """Check if current page has a form. Returns (has_form, field_count)."""
    info = await page.evaluate("""() => {
        const forms = document.querySelectorAll('form');
        let maxFields = 0;
        for (const f of forms) {
            const visible = Array.from(f.querySelectorAll('input,textarea,select'))
                .filter(i => {
                    const t = (i.type||'').toLowerCase();
                    return t !== 'hidden' && t !== 'submit' && t !== 'button' && t !== 'image' && t !== 'reset';
                }).length;
            maxFields = Math.max(maxFields, visible);
        }
        // Also check formless inputs
        if (forms.length === 0) {
            const inputs = document.querySelectorAll('input:not([type=hidden]):not([type=submit]),textarea,select');
            maxFields = inputs.length;
        }
        return {forms: forms.length, maxFields};
    }""")
    return info["maxFields"] >= 2, info["maxFields"]


async def find_form_for_company(page, base_url: str, name: str) -> str | None:
    """Deep crawl to find the form URL for a company. Returns form URL or None."""

    async def try_url(url: str, wait_long: bool = False) -> bool:
        try:
            resp = await page.goto(url, wait_until="load" if wait_long else "domcontentloaded", timeout=20_000)
            if resp is None or resp.status >= 400:
                return False
            if wait_long:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                await page.wait_for_timeout(3000)
            else:
                await page.wait_for_timeout(2000)
            return True
        except Exception:
            return False

    # 1. Load top page
    if not await try_url(base_url):
        return None

    # 2. Find contact links
    links = await find_contact_links_broad(page)

    # 3. Follow each contact link
    for link in links[:5]:
        href = link["href"]
        if not await try_url(href, wait_long=True):
            continue

        has_form, count = await check_page_for_form(page, href)
        if has_form:
            return href

        # 3b. Check iframes on this page
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            frame_url = frame.url or ""
            if any(ad in frame_url.lower() for ad in _AD_IFRAME_PATTERNS):
                continue
            if any(p in frame_url.lower() for p in _FORM_IFRAME_PATTERNS):
                return frame_url

        # 3c. Follow sub-links from contact page (category → form)
        sub_links = await page.evaluate("""() => {
            const kw = ['form', 'inquiry', 'contact', 'input', 'new', 'general'];
            return Array.from(document.querySelectorAll('a[href]'))
                .filter(a => a.href.startsWith('http') && kw.some(k => a.href.toLowerCase().includes(k)))
                .map(a => ({href: a.href, text: (a.innerText||'').trim().substring(0,40)}))
                .slice(0, 5);
        }""")

        for sub in sub_links:
            if not await try_url(sub["href"], wait_long=True):
                continue
            has_form, count = await check_page_for_form(page, sub["href"])
            if has_form:
                return sub["href"]

    # 4. Try sitemap
    sitemap_urls = await find_contact_urls_from_sitemap(page, base_url)
    for surl in sitemap_urls[:3]:
        if not await try_url(surl, wait_long=True):
            continue
        has_form, count = await check_page_for_form(page, surl)
        if has_form:
            return surl

    # 5. Path probe
    base = base_url.rstrip("/")
    for path in _CONTACT_PATHS[:15]:
        candidate = base + path
        if not await try_url(candidate, wait_long=True):
            continue
        has_form, count = await check_page_for_form(page, candidate)
        if has_form:
            return candidate

    return None


async def run(results_csv: str) -> None:
    with open(results_csv, encoding="utf-8") as f:
        no_form = [r for r in csv.DictReader(f) if r["status"] == "form_not_found"]

    cache = load_cache()
    already_cached = sum(1 for r in no_form if domain(r["url"]) in cache)

    print(f"NO FORM: {len(no_form)}社 (うち{already_cached}社はキャッシュ済み)")
    print(f"探索対象: {len(no_form) - already_cached}社")
    print()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    ctx = await browser.new_context(
        locale="ja-JP",
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    )
    page = await ctx.new_page()

    found = 0
    not_found = 0

    for i, r in enumerate(no_form, 1):
        name = r["name"]
        url = r["url"]
        d = domain(url)

        if d in cache:
            print(f"[{i}/{len(no_form)}] {name:22s} CACHED: {cache[d]}")
            continue

        print(f"[{i}/{len(no_form)}] {name:22s}", end=" ... ", flush=True)

        form_url = await find_form_for_company(page, url, name)

        if form_url:
            cache[d] = form_url
            save_cache(cache)
            found += 1
            print(f"FOUND: {form_url}")
        else:
            not_found += 1
            print("NOT FOUND")

    await ctx.close()
    await browser.close()
    await pw.stop()

    print(f"\n{'='*60}")
    print(f"  Cache Build Results")
    print(f"{'='*60}")
    print(f"  New URLs found:  {found}")
    print(f"  Not found:       {not_found}")
    print(f"  Total cache:     {len(cache)} entries")
    print(f"  Cache file:      {CACHE_PATH}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/build_cache.py results/try_XXXXXXX/results.csv")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
