<div align="center">

# 🤖 sales-form-bot

**Playwright + AIで企業の問い合わせフォームを自動検出・入力するボット**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Playwright](https://img.shields.io/badge/playwright-enabled-2EAD33?style=flat-square&logo=playwright&logoColor=white)](https://playwright.dev/)
[![Tests](https://img.shields.io/badge/tests-63%20passing-brightgreen?style=flat-square)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](../LICENSE)

[機能](#機能) · [クイックスタート](#クイックスタート) · [ベンチマーク](#ベンチマーク) · [仕組み](#仕組み) · [English](../README.md)

</div>

---

## 概要

企業URLを渡すだけで、問い合わせフォームを自動検出→フィールドマッピング→人間らしく入力します。

```
入力:  https://example.co.jp + プロフィール（名前、メール、メッセージ等）
出力:  フォーム入力完了 ✓ | スクリーンショット保存 ✓ | 結果CSV出力 ✓
```

**上場企業300社テスト済み**: フォーム発見率81%、入力成功率65%。

## 必要なもの

| 要件 | 理由 |
|------|------|
| Python 3.11+ | 実行環境 |
| Chromium | ヘッドレスブラウザ（Playwrightで自動インストール） |
| 30秒 | 最初のフォーム入力までの時間 |

## クイックスタート

```bash
git clone https://github.com/ShotaNagafuchi/sales-form-bot.git
cd sales-form-bot
pip install -r requirements.txt
playwright install chromium

# ドライラン（入力のみ、送信しない）
python3 scripts/try_forms.py https://example.co.jp

# CSVから一括ベンチマーク
python3 scripts/try_forms.py --csv data/companies.csv --sample 50

# ブラウザを表示して確認
python3 scripts/try_forms.py --headed https://example.co.jp
```

## 機能

### 5層フォーム検出

| レイヤー | 方法 | 検出対象 |
|---------|------|---------|
| キャッシュ | 発見済みURL参照 | 既知サイト（即座） |
| ルールベース | リンク追跡 + iframe + formless input | 標準HTML、CF7、WPForms |
| サブリンク | カテゴリ→フォームの多段ナビ | 「お問い合わせ種別」→実フォーム |
| Sitemap | XML sitemapパース | 大規模サイトの埋もれたURL |
| LLM | AIがcontactページを分析 | 外部ドメイン（Salesforce、kintone等） |

### Hybridフィールドマッピング

5つの戦略を比較テスト。Hybridが全テストで最高:

| 戦略 | 方法 | 入力率 |
|------|------|-------|
| Semantic | ラベルテキストのみ | 33% |
| Sequential | フィールド型で順番入力 | 67% |
| Rule-based | パターンマッチ | 68% |
| **Hybrid** | **ルール優先 + Sequential補完** | **79%** |

### 日本語フォーム完全対応

ふりがな、郵便番号、都道府県、御社名、プライバシーポリシー同意チェック、「その他」セレクト自動選択に対応。

## ベンチマーク

### 上場企業300社テスト

```
フォーム発見:       244/300 (81%)
1+フィールド入力:   195/300 (65%)
50%+フィールド入力: 164/300 (55%)
発見→入力成功:     195/244 (80%)
```

### 業種別発見率

| 業種 | 発見率 |
|------|-------|
| 鉄鋼 | 100% |
| 機械 | 89% |
| 情報・通信業 | 86% |
| サービス業 | 82% |
| 卸売業 | 82% |
| 銀行業 | 14%（Webフォームなし） |

## 仕組み

```
企業URL
  │
  ▼
フォーム検出（5層）→ Hybridマッピング → 人間らしく入力 → 送信+検証 → 結果CSV
```

詳細な方法論は [docs/index.md](index.md) を参照。

## ライセンス

MIT
