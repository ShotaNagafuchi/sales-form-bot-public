"""URL → form page discovery: navigate to URL and find contact forms."""

from __future__ import annotations

from playwright.async_api import Browser, Page, async_playwright

from src.config import BrowserConfig
from src.detector.extractor import extract_forms
from src.detector.models import DetectedForm
from src.detector.sitemap import find_contact_urls_from_sitemap

# Common Japanese contact page paths to probe
_CONTACT_PATHS = [
    "/contact",
    "/contact/",
    "/contact-us",
    "/contact-us/",
    "/inquiry",
    "/inquiry/",
    "/inquiries",
    "/otoiawase",
    "/otoiawase/",
    "/toiawase",
    "/form",
    "/form/",
    "/contactform",
    "/contact_form",
    "/contact/form",
    "/support/contact",
    "/company/contact",
    "/about/contact",
    "/jp/contact",
    "/ja/contact",
    "/info/contact",
    "/corporate/contact",
    # Common in Japanese corporate sites
    "/ir/contact",
    "/ir/inquiry",
    "/company/inquiry",
    "/about/inquiry",
    "/support",
    "/support/",
    "/inquiry/general",
    "/contact/general",
    "/ask",
    "/ask/",
    "/inquire",
    "/inquire/",
]

# Keywords in link text or href that indicate a contact page
_LINK_KEYWORDS = [
    "お問い合わせ",
    "お問合せ",
    "お問い合せ",
    "問い合わせ",
    "問合せ",
    "contact",
    "inquiry",
    "otoiawase",
    "toiawase",
]

# Known external form services hosted in iframes
_FORM_IFRAME_PATTERNS = [
    "formzu.net",
    "form.run",
    "formrun.com",
    "hubspot",
    "hs-form",
    "typeform.com",
    "docs.google.com/forms",
    "forms.gle",
    "kintone",
    "form.kintoneapp",
    "salesforce",
    "webto",
]


async def _create_browser(config: BrowserConfig) -> tuple:
    """Launch playwright and browser. Returns (playwright_instance, browser)."""
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=config.headless)
    return pw, browser


async def _navigate_and_extract(page: Page, url: str) -> list[DetectedForm]:
    """Navigate to URL and extract forms. Returns empty list on failure."""
    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if response is None or response.status >= 400:
            return []

        # Wait for JS frameworks to render forms
        try:
            await page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass
        await page.wait_for_timeout(2000)

        # Try main page forms first
        forms = await extract_forms(page, url)
        if forms:
            return forms

        # Try forms inside iframes
        forms = await _extract_iframe_forms(page, url)
        return forms
    except Exception:
        return []


# Ad/tracking iframe domains to skip (these are never contact forms)
_AD_IFRAME_PATTERNS = [
    "doubleclick.net",
    "criteo.com",
    "microad.jp",
    "socdm.com",
    "ladsp.com",
    "fout.jp",
    "impact-ad.jp",
    "addtoany.com",
    "google.com/recaptcha",
    "googlesyndication.com",
    "googleads.g.doubleclick.net",
    "d2-apps.net",
    "google.com/pagead",
    "decsuite.com",
    "about:blank",
    "javascript:",
]


async def _extract_iframe_forms(page: Page, url: str) -> list[DetectedForm]:
    """Check iframes on the page for forms (e.g. formzu, hubspot, etc.)."""
    try:
        frames = page.frames
        for frame in frames:
            if frame == page.main_frame:
                continue
            frame_url = frame.url or ""

            # Skip known ad/tracking iframes
            if any(ad in frame_url.lower() for ad in _AD_IFRAME_PATTERNS):
                continue

            # Check if this iframe might contain a form
            is_form_iframe = any(p in frame_url.lower() for p in _FORM_IFRAME_PATTERNS)
            if not is_form_iframe and not frame_url:
                continue

            try:
                # Extract forms from the iframe
                form_elements = await frame.query_selector_all("form")
                if not form_elements:
                    continue

                # Use a simplified extraction for iframe forms
                for form_el in form_elements:
                    input_elements = await form_el.query_selector_all(
                        "input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select"
                    )
                    if len(input_elements) >= 1:
                        # Found a real form in an iframe — extract it
                        forms = await extract_forms(frame, frame_url or url)
                        if forms:
                            return forms
            except Exception:
                continue
    except Exception:
        pass
    return []


async def _find_contact_links(page: Page, base_url: str) -> list[str]:
    """Scan the page for contact links — includes <a>, <button>, and onclick elements."""
    links = await page.evaluate(
        """(keywords) => {
            const results = [];
            const seen = new Set();

            // 1. Standard <a> links
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                const text = (a.innerText || '').toLowerCase();
                const hrefLower = href.toLowerCase();
                if (!href.startsWith('http')) continue;
                if (seen.has(href)) continue;
                for (const kw of keywords) {
                    if (text.includes(kw) || hrefLower.includes(kw)) {
                        results.push(href);
                        seen.add(href);
                        break;
                    }
                }
            }

            // 2. Buttons and elements with onclick/data-href that contain contact keywords
            const clickables = document.querySelectorAll('[onclick], [data-href], button, [role="link"], [role="button"]');
            for (const el of clickables) {
                const onclick = el.getAttribute('onclick') || '';
                const dataHref = el.getAttribute('data-href') || '';
                const text = (el.innerText || '').toLowerCase();
                const target = onclick + ' ' + dataHref;

                // Extract URL from onclick (e.g. location.href='...' or window.open('...'))
                const urlMatch = target.match(/(?:location\\.href|window\\.open|href)\\s*=\\s*['"]([^'"]+)['"]/);
                if (urlMatch) {
                    const href = urlMatch[1];
                    if (href.startsWith('http') && !seen.has(href)) {
                        for (const kw of keywords) {
                            if (text.includes(kw) || href.toLowerCase().includes(kw)) {
                                results.push(href);
                                seen.add(href);
                                break;
                            }
                        }
                    }
                }

                // data-href
                if (dataHref.startsWith('http') && !seen.has(dataHref)) {
                    for (const kw of keywords) {
                        if (text.includes(kw) || dataHref.toLowerCase().includes(kw)) {
                            results.push(dataHref);
                            seen.add(dataHref);
                            break;
                        }
                    }
                }
            }

            // 3. Check <area> tags in image maps
            for (const area of document.querySelectorAll('area[href]')) {
                const href = area.href;
                const alt = (area.alt || '').toLowerCase();
                if (!href.startsWith('http') || seen.has(href)) continue;
                for (const kw of keywords) {
                    if (alt.includes(kw) || href.toLowerCase().includes(kw)) {
                        results.push(href);
                        seen.add(href);
                        break;
                    }
                }
            }

            return results;
        }""",
        _LINK_KEYWORDS,
    )
    return links


async def _find_form_sub_links(page: Page) -> list[str]:
    """Find links on a contact category page that might lead to actual forms."""
    links = await page.evaluate(
        """() => {
            const results = [];
            const seen = new Set();
            const keywords = ['inquiry', 'form', 'contact', 'new', 'input'];
            for (const a of document.querySelectorAll('a[href]')) {
                const href = a.href;
                if (!href.startsWith('http')) continue;
                if (seen.has(href)) continue;
                const hrefLower = href.toLowerCase();
                if (keywords.some(k => hrefLower.includes(k))) {
                    results.push(href);
                    seen.add(href);
                }
            }
            return results;
        }"""
    )
    return links[:5]


async def find_forms(
    url: str,
    config: BrowserConfig | None = None,
    browser: Browser | None = None,
) -> list[DetectedForm]:
    """Discover contact forms at the given URL.

    Strategy:
    1. Check the given URL directly for forms (including iframes)
    2. Scan page links for contact page keywords → follow them
    3. Probe common contact page paths as fallback
    """
    cfg = config or BrowserConfig()
    own_browser = browser is None

    pw = None
    if own_browser:
        pw, browser = await _create_browser(cfg)

    try:
        context = await browser.new_context(
            user_agent=cfg.user_agent,
            locale="ja-JP",
        )
        page = await context.new_page()

        # 1. Try the given URL directly (includes iframe detection)
        forms = await _navigate_and_extract(page, url)
        if forms:
            return forms

        # 2. Find contact links on the page and follow them
        contact_links = await _find_contact_links(page, url)
        for link in contact_links[:5]:  # Limit to 5 candidates
            forms = await _navigate_and_extract(page, link)
            if forms:
                return forms

        # 2b. If contact page was found but had no form, check sub-links
        # (handles "category selection → form" pattern)
        if contact_links:
            for link in contact_links[:2]:
                try:
                    await page.goto(link, wait_until="domcontentloaded", timeout=15_000)
                    await page.wait_for_timeout(1500)
                    sub_links = await _find_form_sub_links(page)
                    for sub in sub_links[:3]:
                        forms = await _navigate_and_extract(page, sub)
                        if forms:
                            return forms
                except Exception:
                    continue

        # 3. Check sitemap.xml for contact URLs
        sitemap_urls = await find_contact_urls_from_sitemap(page, url)
        for sitemap_url in sitemap_urls[:5]:
            forms = await _navigate_and_extract(page, sitemap_url)
            if forms:
                return forms

        # 4. Probe common paths as last resort
        base = url.rstrip("/")
        for path in _CONTACT_PATHS:
            candidate = base + path
            forms = await _navigate_and_extract(page, candidate)
            if forms:
                return forms

        return []
    finally:
        if own_browser and browser:
            await browser.close()
        if pw:
            await pw.stop()
