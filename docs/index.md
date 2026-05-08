---
layout: default
title: sales-form-bot
---

# sales-form-bot

Playwright + LLM-powered contact form auto-fill bot for Japanese business outreach.

## Methodology

This document describes the methodology used to build and evaluate sales-form-bot, including the form discovery pipeline, field mapping strategies, and benchmark results across 300+ Japanese listed companies.

---

## 1. Form Discovery Pipeline

Finding contact forms on arbitrary websites is the hardest problem. Companies use different CMS platforms, external form services, JS frameworks, and multi-step navigation patterns.

### 5-Layer Discovery Architecture

| Layer | Method | Cost | Speed | Coverage |
|-------|--------|------|-------|----------|
| 0 | **URL Cache** — previously discovered URLs | Free | Instant | Known sites only |
| 1 | **Rule-based** — link following, iframe scan, formless inputs | Free | Fast | ~77% |
| 2 | **Sitemap.xml** — parse XML sitemap for contact URLs | Free | Medium | +2-3% |
| 3 | **Sub-link crawling** — follow category→form navigation | Free | Slow | +3-5% |
| 4 | **LLM-assisted** — analyze contact page to find form URL | API cost | Slow | +5-10% |

Each layer is tried in order. The first to find a form wins. Layer 4 (LLM) automatically caches discovered URLs, so subsequent runs use Layer 0 instead.

### Why Not Just Use LLM for Everything?

- **Cost**: LLM calls cost money per company. Cache makes it a one-time cost.
- **Speed**: Rule-based discovery takes 2-5 seconds. LLM adds 5-10 seconds.
- **Reliability**: Rule-based is deterministic. LLM can hallucinate URLs.
- **Offline**: Rule-based works without API keys.

The hybrid approach gives us 81% discovery with zero API cost for known companies.

### Failure Analysis

We diagnosed every "not found" case across 300 companies:

| Category | Count | Fixable? |
|----------|-------|----------|
| JS-rendered (React/Vue SPA) | ~16 | Yes, with URL cache |
| External form service (kintone, Salesforce) | ~8 | Yes, with URL cache |
| No web form exists (phone/email only) | ~20 | No |
| Bot blocked (403/WAF) | ~5 | Difficult |
| DNS/SSL errors | ~6 | No (site issue) |

**Key insight**: ~10% of Japanese listed companies have no web contact form at all. This is the hard ceiling for any automated approach.

---

## 2. Field Mapping Strategies

Once a form is found, we need to match profile data (name, email, company, message) to form fields that have arbitrary labels, names, and structures.

### Strategy Comparison

We tested 5 strategies on 20 companies with detected forms:

| Strategy | Approach | Fill Rate | Wins |
|----------|----------|-----------|------|
| **A: Rule-based** | Pattern match on label/name/placeholder | 68% | 4/11 |
| **B: Name-attr** | Use only `[name]` selectors | 67% | 3/11 |
| **C: Semantic** | Match by label/placeholder text only | 33% | 4/11 |
| **D: Sequential** | Fill fields top-to-bottom by type | 67% | 6/11 |
| **Hybrid (A+D)** | Rule-based first, sequential fills gaps | **79%** | **11/11** |

### Why Hybrid Wins

- **Rule-based (A)** is accurate when labels match known patterns ("お名前" → name, "メール" → email)
- **Sequential (D)** handles unknown fields by type inference (first email input → email, first textarea → message)
- **Hybrid** uses rule-based for confident matches, then sequential fills any remaining gaps
- Result: **Hybrid never lost to any other strategy** across all tested companies

### Japanese Form Patterns

Common field mappings for Japanese corporate contact forms:

| Form Label | Profile Field | Notes |
|-----------|---------------|-------|
| お名前, 氏名, 担当者名 | name | |
| ふりがな, フリガナ | furigana | Hiragana/katakana reading |
| 会社名, 御社名, 貴社名 | company_name | |
| メールアドレス, E-mail | email | |
| 電話番号, TEL | phone | Auto-formatted with hyphens |
| 郵便番号, 〒 | zip | |
| 住所, 所在地 | address | |
| お問い合わせ内容, メッセージ | message | |
| プライバシーポリシーに同意 | (auto-check) | Always checked |
| お問い合わせ種別 (select) | (fallback: "その他") | Picks safest option |

### Normalization

Values are automatically normalized for the target field type:

- **Phone**: `0312345678` → `03-1234-5678` (landline) or `09012345678` → `090-1234-5678` (mobile)
- **Email**: trimmed, lowercased, format validated
- **URL**: `example.com` → `https://example.com`

---

## 3. Benchmark Methodology

### Test Setup

- **Source**: Tokyo Stock Exchange listed companies (~3,800)
- **Sampling**: Random sample with fixed seed for reproducibility
- **Mode**: Dry run (fills form but does not submit)
- **Browser**: Headless Chromium via Playwright
- **Profile**: Fixed test profile with all fields populated

### Metrics

| Metric | Definition |
|--------|-----------|
| **Form Discovery** | % of companies where a contact form was found |
| **E2E Fill (1+)** | % of companies where at least 1 field was filled |
| **E2E Fill (50%+)** | % of companies where half or more fields were filled |
| **Field Fill Rate** | Total fields filled / total fields detected |
| **Found→Filled** | % of discovered forms that were successfully filled |

### 300-Company Results

```
                     Discovery   E2E(1+)   E2E(50%+)   Field Rate
Baseline              58%        44%        —           —
+ iframe/JS           86%        50%        —           —
+ Hybrid mapping      76%        63%        51%         59%
+ Sub-link/sitemap    77%        56%        47%         54%
+ Re-navigate fix     77%        61%        50%         58%
+ URL cache (43)      81%        65%        55%         60%
```

### Reproducibility

All benchmarks use fixed random seeds:

```bash
# Reproduce the 300-company benchmark
python3 scripts/try_forms.py --csv data/companies.csv --sample 300 --seed 777

# Reproduce strategy comparison
python3 scripts/compare_strategies.py --csv data/companies.csv --sample 20 --seed 200
```

---

## 4. URL Cache System

The cache (`data/form_url_cache.json`) stores discovered form URLs per domain:

```json
{
  "www.sevenbank.co.jp": "https://req.qubo.jp/sevenbank-hojin-service/form/VExIUlQZ",
  "www.adastria.co.jp": "https://adastriacorporate.zendesk.com/hc/ja/requests/new"
}
```

### How It Works

1. **First visit**: Bot crawls site → finds form → caches URL
2. **Subsequent visits**: Bot reads cache → goes directly to form URL
3. **LLM mode**: If crawling fails, LLM analyzes contact page → identifies form URL → caches

### Cache Building

```bash
# Auto-build cache from benchmark results
python3 scripts/build_cache.py results/try_*/results.csv

# Manual addition
# Edit data/form_url_cache.json directly
```

### Cache Impact

| Metric | Without Cache | With Cache (43 entries) |
|--------|--------------|------------------------|
| Discovery | 77% | 81% |
| E2E Fill | 61% | 65% |

---

## 5. Limitations and Future Work

### Current Limitations

- **CAPTCHA**: Not yet handled (reCAPTCHA, Turnstile). Forms with CAPTCHA are skipped.
- **File uploads**: Not supported. File upload fields are skipped.
- **Multi-page forms**: Only single-page forms are supported.
- **Rate limiting**: Fixed daily cap (10/day) but no adaptive rate limiting.

### Theoretical Ceiling

Based on our analysis of 300 Japanese listed companies:

- **~90%** have a web contact form somewhere (reachable with cache + LLM)
- **~10%** accept inquiries only by phone, email, or in-person
- **~80%** of found forms can be filled with the hybrid mapping strategy
- **Theoretical max E2E rate: ~72%** (90% discovery × 80% fill)
- **Current: 65%** — 90% of theoretical maximum

### Future Improvements

| Improvement | Expected Impact | Complexity |
|-------------|----------------|------------|
| CAPTCHA solving (2Captcha API) | +3-5% E2E | Medium |
| LLM auto-cache (Haiku) | +5-8% discovery | Low |
| Residential proxy rotation | +2-3% (bot block) | Medium |
| Multi-page form support | +1-2% | High |
