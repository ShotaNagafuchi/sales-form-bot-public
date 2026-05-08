"""LLM-based form URL discovery: analyze contact pages to find actual form URLs."""

from __future__ import annotations

import json
import os

import anthropic
from playwright.async_api import Page

from src.config import LLMConfig

_SYSTEM_PROMPT = """\
You are a web form locator. Given the text content and links from a contact page, \
identify the URL where the actual inquiry/contact form is located.

The form might be:
- On the current page (if it has input fields)
- Behind a link on the page (e.g. "お問い合わせはこちら" button)
- On an external domain (e.g. formzu.net, qubo.jp, hubspot, salesforce)
- Behind a category selection (e.g. "法人のお客様" → form)

Rules:
- Return the MOST LIKELY form URL for general business inquiries
- Prefer "一般" or "その他" category if there are multiple options
- If the page itself IS the form (has input fields), return "CURRENT_PAGE"
- If no form can be identified, return "NOT_FOUND"

Respond with ONLY the URL (or CURRENT_PAGE or NOT_FOUND). No explanation."""


async def find_form_url_with_llm(
    page: Page,
    contact_page_url: str,
    config: LLMConfig | None = None,
) -> str | None:
    """Use LLM to analyze a contact page and identify the actual form URL.

    Returns the form URL, "CURRENT_PAGE" if form is on the current page, or None if not found.
    """
    cfg = config or LLMConfig()
    if not cfg.api_key:
        return None

    # Gather page info for LLM
    page_info = await _extract_page_info(page)
    if not page_info:
        return None

    user_prompt = (
        f"URL: {contact_page_url}\n\n"
        f"Page title: {page_info['title']}\n\n"
        f"Links on page:\n{page_info['links']}\n\n"
        f"Text content (first 2000 chars):\n{page_info['text'][:2000]}\n\n"
        f"Iframes:\n{page_info['iframes']}"
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=cfg.api_key)
        response = await client.messages.create(
            model=cfg.model,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        result = response.content[0].text.strip()

        if result == "NOT_FOUND":
            return None
        if result == "CURRENT_PAGE":
            return contact_page_url
        if result.startswith("http"):
            return result
        return None

    except Exception:
        return None


async def _extract_page_info(page: Page) -> dict | None:
    """Extract structured info from the current page for LLM analysis."""
    try:
        info = await page.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({text: (a.innerText || '').trim().substring(0, 60), href: a.href}))
                    .filter(a => a.text && a.href.startsWith('http'))
                    .slice(0, 30)
                    .map(a => `${a.text} → ${a.href}`)
                    .join('\\n');

                const iframes = Array.from(document.querySelectorAll('iframe'))
                    .map(f => f.src)
                    .filter(Boolean)
                    .join('\\n');

                return {
                    title: document.title || '',
                    text: (document.body?.innerText || '').substring(0, 2000),
                    links,
                    iframes,
                };
            }"""
        )
        return info
    except Exception:
        return None


class FormURLCache:
    """Persistent cache of discovered form URLs per domain."""

    def __init__(self, cache_path: str = "data/form_url_cache.json"):
        self.cache_path = cache_path
        self._cache: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                self._cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        with open(self.cache_path, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)

    def get(self, url: str) -> str | None:
        """Get cached form URL for a domain."""
        domain = self._extract_domain(url)
        return self._cache.get(domain)

    def set(self, url: str, form_url: str) -> None:
        """Cache a discovered form URL for a domain."""
        domain = self._extract_domain(url)
        self._cache[domain] = form_url
        self.save()

    def has(self, url: str) -> bool:
        domain = self._extract_domain(url)
        return domain in self._cache

    @staticmethod
    def _extract_domain(url: str) -> str:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or url

    @property
    def size(self) -> int:
        return len(self._cache)
