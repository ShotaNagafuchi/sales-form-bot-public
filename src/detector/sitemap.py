"""Discover contact form URLs from sitemap.xml."""

from __future__ import annotations

import re

from playwright.async_api import Page

_CONTACT_PATTERNS = re.compile(
    r"(contact|inquiry|otoiawase|toiawase|form|inquir)",
    re.IGNORECASE,
)

_EXCLUDE_PATTERNS = re.compile(
    r"(news|blog|press|\.pdf|faq|privacy|terms|policy|information_\d|category|tag/)",
    re.IGNORECASE,
)


async def find_contact_urls_from_sitemap(page: Page, base_url: str) -> list[str]:
    """Parse sitemap.xml and return URLs that look like contact/inquiry pages."""
    sitemap_url = base_url.rstrip("/") + "/sitemap.xml"
    return await _parse_sitemap(page, sitemap_url, depth=0)


async def _parse_sitemap(page: Page, sitemap_url: str, depth: int = 0) -> list[str]:
    """Fetch and parse a sitemap, returning contact-related URLs."""
    if depth > 1:
        return []

    try:
        resp = await page.goto(sitemap_url, wait_until="domcontentloaded", timeout=10_000)
        if resp is None or resp.status != 200:
            return []

        content = await page.evaluate(
            "() => new XMLSerializer().serializeToString(document)"
        )

        # Extract all <loc> URLs
        all_locs = re.findall(r"<loc>(https?://[^<]+)</loc>", content)
        if not all_locs:
            return []

        # Check if this is a sitemap index (locs point to other sitemaps)
        sitemap_locs = [u for u in all_locs if "sitemap" in u.lower() and u.endswith(".xml")]
        if sitemap_locs and depth == 0:
            all_urls: list[str] = []
            for sub in sitemap_locs[:3]:
                sub_urls = await _parse_sitemap(page, sub, depth=depth + 1)
                all_urls.extend(sub_urls)
            if all_urls:
                return all_urls
            # Fall through to check current sitemap's URLs too

        # Filter for contact-related URLs
        contact_urls = []
        for url in all_locs:
            if _CONTACT_PATTERNS.search(url) and not _EXCLUDE_PATTERNS.search(url):
                contact_urls.append(url)

        # Sort: prefer shorter URLs (more likely to be the main contact page)
        contact_urls.sort(key=len)
        return contact_urls[:5]

    except Exception:
        return []
