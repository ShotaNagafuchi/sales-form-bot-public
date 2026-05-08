"""Diagnose why forms were not found — check each NO FORM URL for:
1. Does the top page load at all?
2. Are there contact links on the page?
3. Do the contact links lead to a form?
4. What kind of form is it (iframe, external service, JS-rendered)?

Usage:
    python3 scripts/diagnose_no_form.py results/try_XXXXXXX/results.csv
"""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright

from src.detector.extractor import extract_forms
from src.detector.finder import _CONTACT_PATHS, _LINK_KEYWORDS


async def diagnose_url(page, url: str, name: str) -> dict:
    """Diagnose why a form wasn't found at this URL."""
    result = {
        "name": name,
        "url": url,
        "page_loads": False,
        "contact_links": [],
        "contact_link_count": 0,
        "form_on_contact_page": False,
        "form_page_url": "",
        "has_iframe_form": False,
        "has_external_form": False,
        "form_field_count": 0,
        "diagnosis": "",
    }

    # 1. Check if page loads
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        if resp is None or resp.status >= 400:
            result["diagnosis"] = f"PAGE_LOAD_FAIL (status={resp.status if resp else 'none'})"
            return result
        result["page_loads"] = True
        await page.wait_for_timeout(1500)
    except Exception as e:
        result["diagnosis"] = f"PAGE_LOAD_ERROR ({str(e)[:80]})"
        return result

    # 2. Find contact links
    links = await page.evaluate(
        """(keywords) => {
            const results = [];
            const seen = new Set();
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                const text = (a.innerText || '').trim();
                const hrefLower = href.toLowerCase();
                if (!href.startsWith('http')) continue;
                if (seen.has(href)) continue;
                const textLower = text.toLowerCase();
                for (const kw of keywords) {
                    if (textLower.includes(kw) || hrefLower.includes(kw)) {
                        results.push({href, text: text.substring(0, 50)});
                        seen.add(href);
                        break;
                    }
                }
            }
            return results;
        }""",
        _LINK_KEYWORDS,
    )
    result["contact_links"] = links
    result["contact_link_count"] = len(links)

    # 3. Check for iframe forms on current page
    iframe_info = await page.evaluate(
        """() => {
            const iframes = document.querySelectorAll('iframe');
            const formIframes = [];
            for (const iframe of iframes) {
                const src = iframe.src || '';
                if (src.includes('form') || src.includes('contact') || src.includes('inquiry')) {
                    formIframes.push(src);
                }
            }
            return formIframes;
        }"""
    )
    if iframe_info:
        result["has_iframe_form"] = True
        result["diagnosis"] = f"IFRAME_FORM ({iframe_info[0][:100]})"
        return result

    # 4. Follow contact links and check for forms
    for link_info in links[:5]:
        link = link_info["href"]
        try:
            resp = await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
            if resp and resp.status < 400:
                await page.wait_for_timeout(1500)

                # Check for iframe forms on contact page
                iframe_info = await page.evaluate(
                    """() => {
                        const iframes = document.querySelectorAll('iframe');
                        const results = [];
                        for (const iframe of iframes) {
                            const src = iframe.src || '';
                            if (src) results.push(src.substring(0, 100));
                        }
                        return results;
                    }"""
                )

                forms = await extract_forms(page, link)
                if forms:
                    result["form_on_contact_page"] = True
                    result["form_page_url"] = link
                    result["form_field_count"] = len(forms[0].fields)
                    result["diagnosis"] = f"FORM_FOUND_ON_LINK (fields={len(forms[0].fields)}, missed by finder)"
                    return result

                # Check for external form services
                external = await page.evaluate(
                    """() => {
                        const html = document.body?.innerHTML || '';
                        const signals = [];
                        if (html.includes('googleusercontent.com') || html.includes('docs.google.com/forms'))
                            signals.push('google_form');
                        if (html.includes('hubspot') || html.includes('hs-form'))
                            signals.push('hubspot');
                        if (html.includes('salesforce') || html.includes('webto'))
                            signals.push('salesforce');
                        if (html.includes('formrun') || html.includes('form.run'))
                            signals.push('formrun');
                        if (html.includes('typeform'))
                            signals.push('typeform');
                        if (html.includes('kintone'))
                            signals.push('kintone');

                        const iframes = document.querySelectorAll('iframe');
                        for (const iframe of iframes) {
                            signals.push('iframe:' + (iframe.src || '').substring(0, 80));
                        }
                        return signals;
                    }"""
                )
                if external:
                    result["has_external_form"] = True
                    result["diagnosis"] = f"EXTERNAL_FORM ({', '.join(external[:3])})"
                    return result

                # Check if form exists but with < 2 visible fields (our filter)
                raw_forms = await page.evaluate(
                    """() => {
                        const forms = document.querySelectorAll('form');
                        return Array.from(forms).map(f => ({
                            fields: f.querySelectorAll('input,textarea,select').length,
                            action: f.action?.substring(0, 80) || '',
                            id: f.id || '',
                            class: f.className?.substring(0, 50) || '',
                        }));
                    }"""
                )
                if raw_forms:
                    result["diagnosis"] = f"FORM_FILTERED_OUT (forms={len(raw_forms)}, fields={[f['fields'] for f in raw_forms]})"
                    return result

        except Exception:
            continue

    # 5. Probe common paths
    base = url.rstrip("/")
    for path in _CONTACT_PATHS[:8]:
        try:
            candidate = base + path
            resp = await page.goto(candidate, wait_until="domcontentloaded", timeout=10_000)
            if resp and resp.status < 400:
                await page.wait_for_timeout(1000)
                forms = await extract_forms(page, candidate)
                if forms:
                    result["form_on_contact_page"] = True
                    result["form_page_url"] = candidate
                    result["form_field_count"] = len(forms[0].fields)
                    result["diagnosis"] = f"FORM_ON_PROBED_PATH (path={path}, fields={len(forms[0].fields)})"
                    return result
        except Exception:
            continue

    # No form found anywhere
    if links:
        result["diagnosis"] = f"NO_FORM_DESPITE_LINKS (links={len(links)})"
    else:
        result["diagnosis"] = "NO_CONTACT_LINKS_FOUND"

    return result


async def run(results_csv: str) -> None:
    # Load NO FORM URLs
    targets = []
    with open(results_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["status"] == "form_not_found":
                targets.append({"name": row["name"], "url": row["url"]})

    print(f"Diagnosing {len(targets)} NO FORM cases...\n")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(locale="ja-JP")
    page = await context.new_page()

    diagnoses: dict[str, list] = {}

    for i, t in enumerate(targets, 1):
        print(f"[{i}/{len(targets)}] {t['name']:20s}", end=" ... ", flush=True)
        result = await diagnose_url(page, t["url"], t["name"])
        print(result["diagnosis"])

        diag = result["diagnosis"].split(" ")[0]
        diagnoses.setdefault(diag, []).append(result)

    await context.close()
    await browser.close()
    await pw.stop()

    # Summary
    print(f"\n{'='*60}")
    print(f"  DIAGNOSIS SUMMARY")
    print(f"{'='*60}")
    for diag, items in sorted(diagnoses.items(), key=lambda x: -len(x[1])):
        print(f"  {diag:<35} {len(items)} cases")
        for item in items[:3]:
            print(f"    - {item['name']}: {item['url']}")
        if len(items) > 3:
            print(f"    ... and {len(items)-3} more")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/diagnose_no_form.py results/try_XXXXXXX/results.csv")
        sys.exit(1)
    asyncio.run(run(sys.argv[1]))


if __name__ == "__main__":
    main()
