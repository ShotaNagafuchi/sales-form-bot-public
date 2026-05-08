<div align="center">

# 🤖 sales-form-bot

**Auto-discover and fill contact forms on any website with Playwright + AI**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-enabled-2EAD33?style=flat-square&logo=playwright&logoColor=white)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/tests-63%20passing-brightgreen?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

[Features](#features) · [Quick Start](#quick-start) · [Benchmarks](#benchmarks) · [How It Works](#how-it-works) · [日本語](docs/README_ja.md)

</div>

---

## What It Does

Give it a company URL. It finds the contact form, maps your data to the fields, and fills it — with human-like typing.

```
Input:  https://example.co.jp + your profile (name, email, message...)
Output: Form filled ✓ | Screenshot saved ✓ | Result logged ✓
```

Works on **300+ tested Japanese listed companies** with 81% form discovery and 65% end-to-end fill rate.

## What You Need

| Requirement | Why |
|-------------|-----|
| Python 3.11+ | Runtime |
| Chromium | Headless browser (auto-installed via Playwright) |
| 30 seconds | Time to first form fill |

Optional: Anthropic API key for LLM-assisted form discovery on hard-to-find forms.

## Quick Start

```bash
git clone https://github.com/ShotaNagafuchi/sales-form-bot.git
cd sales-form-bot
pip install -r requirements.txt
playwright install chromium

# Fill a form (dry run — no actual submission)
python3 scripts/try_forms.py https://example.co.jp

# Batch benchmark from CSV
python3 scripts/try_forms.py --csv data/companies.csv --sample 50

# Watch it work (opens browser window)
python3 scripts/try_forms.py --headed https://example.co.jp
```

## Features

### 🔍 5-Layer Form Discovery

Most bots just look for `<form>` tags. Real-world contact forms are behind JavaScript, iframe embeds, multi-step navigation, and external services.

| Layer | Method | What It Catches |
|-------|--------|-----------------|
| Cache | Previously discovered URLs | Instant lookup for known sites |
| Rule-based | Link following + iframe + formless inputs | Standard HTML forms, CF7, WPForms |
| Sub-link | Category → form navigation | "Choose inquiry type" → actual form |
| Sitemap | XML sitemap parsing | Contact URLs buried in large sites |
| LLM | AI analyzes contact page → finds form URL | External domains (Salesforce, kintone, Zendesk) |

### 🧠 Hybrid Field Mapping

Tested 5 strategies. Hybrid won every comparison:

| Strategy | How It Works | Fill Rate |
|----------|-------------|-----------|
| Semantic | Label text only | 33% |
| Name-attr | `name` attribute only | 67% |
| Sequential | Fill by field type order | 67% |
| Rule-based | Pattern matching (名前→name, メール→email) | 68% |
| **Hybrid** | **Rule-based first, sequential fills gaps** | **79%** |

### 🌏 International + Japanese Support

Built for Japanese business forms, works globally:

```
English:  Name, Email, Company, Phone, Message
Japanese: お名前, ふりがな, 会社名, 電話番号, お問い合わせ内容
```

Handles: furigana (ふりがな/フリガナ), Japanese phone formatting (03-1234-5678), postal codes, prefecture fields, privacy policy checkboxes, "その他" select fallback.

### 🎭 Human-like Interaction

| Behavior | Implementation |
|----------|---------------|
| Typing speed | 50-150ms per character, random pauses |
| Cursor movement | Click within bounds with jitter offset |
| Field transitions | 500-2000ms delay between fields |
| Scrolling | Natural scroll-into-view for off-screen elements |
| Page load | Wait for networkidle + JS rendering |

### 📊 Supported Form Platforms

| Platform | Detection Method |
|----------|-----------------|
| Generic HTML `<form>` | Direct extraction |
| WordPress Contact Form 7 | `.wpcf7-form` parser |
| WPForms | `.wpforms-form` parser |
| Google Forms | `data-params` / `role` parser |
| Formzu, Formrun | Iframe detection |
| Kintone, Salesforce, HubSpot | URL cache + LLM discovery |
| Zendesk | URL cache + patient wait |
| React/Vue SPAs | Formless input detection |

## Benchmarks

### 300-Company Test (Japanese TSE-listed)

```
Form Discovery:       244/300  (81%)
Filled 1+ fields:     195/300  (65%)
Filled 50%+ fields:   164/300  (55%)
If found → filled:    195/244  (80%)
```

### Improvement History

| Version | Discovery | E2E Fill | Key Change |
|---------|-----------|----------|------------|
| v0.1 Baseline | 58% | 44% | Rule-based only |
| v0.2 | 86% | 50% | + iframe, JS-wait, formless inputs |
| v0.3 | 76% | 63% | + Hybrid mapping strategy |
| v0.4 | 77% | 61% | + Sub-link, sitemap, re-navigate fix |
| **v0.5** | **81%** | **65%** | **+ URL cache (43 entries)** |

### Industry Performance

| Industry | Discovery | Best For |
|----------|-----------|----------|
| Steel (鉄鋼) | 100% | Manufacturing outreach |
| Machinery (機械) | 89% | Industrial sales |
| IT/Telecom (情報通信) | 86% | Tech partnerships |
| Services (サービス) | 82% | General business |
| Wholesale (卸売) | 82% | Trade inquiries |
| Banking (銀行) | 14% | Most have no web form |

### Theoretical Ceiling

- ~90% of companies have a reachable web form (with cache + LLM)
- ~80% of found forms can be filled with hybrid mapping
- **Max achievable: ~72%** | Current: 65% (90% of theoretical max)

## How It Works

```
Company URL
    │
    ▼
┌─────────────────────────────────┐
│  Form Discovery (5 layers)      │
│  Cache → Links → Sub-links      │
│  → Sitemap → LLM                │
└──────────────┬──────────────────┘
               │ DetectedForm (fields, selectors, submit button)
               ▼
┌─────────────────────────────────┐
│  Hybrid Mapper                  │
│  Rule-based patterns first      │
│  Sequential fallback for gaps   │
│  + Normalize (phone, email)     │
└──────────────┬──────────────────┘
               │ ValidatedMappings
               ▼
┌─────────────────────────────────┐
│  Form Filler (Playwright)       │
│  Human-like typing + jitter     │
│  Re-navigate to form URL        │
└──────────────┬──────────────────┘
               │
               ▼
┌─────────────────────────────────┐
│  Submit + Verify                │
│  Success/failure detection      │
│  Before/after screenshots       │
└──────────────┬──────────────────┘
               │
               ▼
           Results CSV + Screenshots
```

## Profile Configuration

Create your sender profile:

```bash
cp profiles/default.json profiles/myprofile.json
```

```json
{
  "company_name": "Acme Corporation",
  "name": "Taro Yamada",
  "email": "taro@example.com",
  "phone": "03-1234-5678",
  "message": "I'd like to discuss a potential collaboration..."
}
```

For Japanese outreach, use `profiles/example_ja.json` as a template — includes furigana, postal code, and keigo message.

```bash
python3 scripts/try_forms.py --profile profiles/myprofile.json https://example.co.jp
```

## CLI Reference

```bash
# Single URL
python3 scripts/try_forms.py https://example.co.jp

# Batch from CSV (random sample)
python3 scripts/try_forms.py --csv data/companies.csv --sample 100 --seed 42

# Headed mode (watch the browser)
python3 scripts/try_forms.py --headed https://example.co.jp

# Custom profile
python3 scripts/try_forms.py --profile profiles/myprofile.json URL

# Actually submit (use with caution)
python3 scripts/try_forms.py --submit URL

# Compare mapping strategies
python3 scripts/compare_strategies.py --csv data/companies.csv --sample 20

# Build URL cache for hard-to-find forms
python3 scripts/build_cache.py results/try_*/results.csv

# Diagnose why forms weren't found
python3 scripts/diagnose_no_form.py results/try_*/results.csv
```

## Project Structure

```
src/
├── detector/           # Form discovery
│   ├── finder.py       # 5-layer discovery pipeline
│   ├── extractor.py    # DOM → field extraction
│   ├── sitemap.py      # XML sitemap parser
│   ├── llm_finder.py   # LLM discovery + URL cache
│   └── parsers/        # CF7, WPForms, Google Forms
├── mapper/             # Field mapping
│   ├── strategies.py   # 5 strategies (Hybrid is default)
│   ├── normalizer.py   # Phone/email/URL normalization
│   └── validator.py    # Confidence + required field checks
├── filler/             # Form filling
│   ├── engine.py       # Playwright input engine
│   └── humanizer.py    # Human-like delays + jitter
├── submitter/          # Submit + verify
│   ├── submit.py       # Click submit, handle SPA/navigation
│   ├── verifier.py     # Success/failure text detection
│   └── screenshot.py   # Before/after captures
├── queue/              # Job pipeline
│   ├── consumer.py     # Full pipeline orchestrator
│   └── models.py       # Pydantic schemas
├── config.py           # Settings
└── profile.py          # Profile loader
```

## Roadmap

| Feature | Status |
|---------|--------|
| Multi-layer form discovery | ✅ Done |
| Hybrid field mapping | ✅ Done |
| Human-like form filling | ✅ Done |
| Submission + verification | ✅ Done |
| URL cache system | ✅ Done |
| Benchmark framework | ✅ Done |
| 300-company benchmark | ✅ Done |
| CAPTCHA handling (2Captcha) | 🔜 Planned |
| LLM auto-discovery (Haiku) | 🔜 Planned |
| Docker deployment | 🔜 Planned |
| Redis job queue | 🔜 Planned |
| Multi-language form support | 🔜 Planned |

## Why Not Just Use [X]?

| Tool | Limitation | sales-form-bot Advantage |
|------|-----------|-------------------------|
| Selenium scripts | Breaks on unknown forms | Adaptive discovery + mapping |
| Browser extensions | Manual, no batch | CLI batch processing |
| SaaS form fillers | Expensive, US-focused | Free, Japanese-first |
| Generic RPA | No form-finding intelligence | 5-layer auto-discovery |
| LLM-only approach | Slow, expensive per form | Rule-based first, LLM only when needed |

## Contributing

PRs welcome. Key areas:
- New form platform parsers (Gravity Forms, Wix, etc.)
- Additional mapping patterns for non-Japanese forms
- CAPTCHA solving integrations
- Performance improvements

## License

MIT — see [LICENSE](LICENSE)
