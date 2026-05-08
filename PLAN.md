# sales-form-bot — フォーム自動入力・送信パイプライン

## 概要

営業リードの問い合わせフォームを自動検出・入力・送信するPlaywright + LLMベースのボット。
`sales-ai` リポジトリからジョブキュー（JSON）を受け取り、非同期でフォーム送信を実行する。

## 参考リポジトリ

| リポジトリ | 取り込むポイント |
|---|---|
| **Form-Flow-AI** | LLMフォーム構造認識、フィールドタイプ正規化、CAPTCHA多段戦略、ヒューマニゼーション（typing delay + cursor jitter） |
| **arthurbabin/ai-form-filler** | シンプルなローカル保存アーキ、拡張性の高いミニマル設計 |
| **Playwrightベースjob application bots** | URL→フォーム検出→入力→送信の基本フロー |

## アーキテクチャ

```
sales-ai (既存)                    sales-form-bot (本リポ)
┌─────────────────┐               ┌─────────────────────────────┐
│ Lead DB         │               │                             │
│ + パーソナライズ │──── JSON ────→│  Queue Consumer             │
│   文面生成      │   (queue/)    │    ↓                        │
└─────────────────┘               │  Form Detector (Playwright) │
                                  │    ↓                        │
                                  │  Field Mapper (LLM)         │
                                  │    ↓                        │
                                  │  Form Filler (Playwright)   │
                                  │    ↓                        │
                                  │  Submitter + Verifier       │
                                  │    ↓                        │
                                  │  Result Reporter → sales-ai │
                                  └─────────────────────────────┘
```

## ディレクトリ構成

```
sales-form-bot/
├── src/
│   ├── queue/
│   │   ├── consumer.py          # JSONキュー読み取り（将来Redis対応）
│   │   └── models.py            # ジョブスキーマ（Pydantic）
│   ├── detector/
│   │   ├── finder.py            # URL → フォームページ発見
│   │   ├── extractor.py         # DOM解析 → フィールドリスト抽出
│   │   └── parsers/
│   │       ├── generic.py       # 汎用HTMLフォーム
│   │       ├── google_form.py   # Google Forms対応
│   │       └── wordpress.py     # Contact Form 7 / WPForms
│   ├── mapper/
│   │   ├── field_mapper.py      # LLMでフィールド意味推定 → データマッピング
│   │   ├── normalizer.py        # フィールドタイプ別正規化（dropdown, email, phone, name）
│   │   └── validator.py         # マッピング検証（不明フィールドはスキップ）
│   ├── filler/
│   │   ├── engine.py            # Playwright入力エンジン
│   │   ├── humanizer.py         # typing delay (50-150ms), cursor jitter, scroll
│   │   └── captcha/
│   │       ├── detector.py      # CAPTCHA種別検出
│   │       ├── turnstile.py     # Cloudflare Turnstile対応
│   │       ├── recaptcha.py     # reCAPTCHA v2/v3（2Captcha API）
│   │       └── fallback.py      # 手動介入 or スキップ
│   ├── submitter/
│   │   ├── submit.py            # 送信ボタン検出 + クリック
│   │   ├── verifier.py          # 送信成功/失敗判定（サンキューページ検出）
│   │   └── screenshot.py        # 送信前後スクリーンショット保存
│   ├── reporter/
│   │   ├── result.py            # 結果JSONをsales-ai/data/に書き戻し
│   │   └── notifier.py          # Slack/メール通知（失敗時）
│   └── config.py                # 設定（LLM provider, timeout, concurrency）
├── profiles/
│   └── default.json             # 送信者プロフィール（会社名、メアド、電話、要件テンプレ）
├── queue/
│   └── pending/                 # sales-aiから投入されるジョブJSON
├── results/
│   └── completed/               # 処理済み結果
├── tests/
│   ├── test_detector.py
│   ├── test_mapper.py
│   ├── test_filler.py
│   └── fixtures/
│       └── sample_forms/        # テスト用HTMLフォーム
├── Dockerfile                   # ヘッドレスChrome + Python環境
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## フェーズ別実装計画

### Phase 1: フォーム検出 + フィールド抽出（MVP）
**目標**: URLを渡すとフォームフィールド一覧をJSON出力

1. Playwright セットアップ（ヘッドレスChromium）
2. URL訪問 → `<form>` / `<input>` / `<textarea>` / `<select>` 検出
3. フィールド属性抽出（name, type, placeholder, label, required, options）
4. Contact Form 7 / WPForms の特殊マークアップ対応
5. テスト: 10サイトでフォーム検出率80%以上

**参考**: Form-Flow-AI の `extractor.py` + factory pattern

### Phase 2: LLMフィールドマッピング
**目標**: 抽出フィールドと送信データを自動マッチング

1. フィールドリスト + プロフィールデータをLLMに渡す
2. セマンティックマッピング（「御社名」→ company_name, 「ご用件」→ message）
3. ドロップダウン: 選択肢とのfuzzy match → 不一致はスキップ
4. フィールドタイプ別正規化（電話ハイフン、メール形式チェック）
5. マッピング結果のconfidenceスコア → 閾値以下は人間レビュー

**参考**: Form-Flow-AI の `llm_extractor.py` + `normalizer` パターン

### Phase 3: 自動入力 + ヒューマニゼーション
**目標**: マッピング済みデータをフォームに人間らしく入力

1. Playwright で各フィールドにfocus → 入力
2. typing delay: 50-150ms/char（ランダム）
3. フィールド間の遅延: 500-2000ms
4. スクロール挙動: フィールドが画面外なら自然にスクロール
5. ドロップダウン: click → 選択肢表示待ち → 選択
6. チェックボックス/ラジオ: 適切な値を選択
7. 入力後スクリーンショット保存

**参考**: Form-Flow-AI のヒューマニゼーション戦略

### Phase 4: CAPTCHA対応
**目標**: 一般的なCAPTCHAを突破 or 適切にスキップ

1. CAPTCHA種別自動検出（iframe src, class名, script tag）
2. Turnstile: stealth mode + 自動待機
3. reCAPTCHA v2: 2Captcha API連携（有料、1件$0.003程度）
4. reCAPTCHA v3: スコアベースなので通常はヒューマニゼーションで突破
5. 解決不能: スキップ + 結果レポートに「CAPTCHA_BLOCKED」記録

**参考**: Form-Flow-AI の多段CAPTCHA戦略

### Phase 5: 送信 + 結果検証
**目標**: 送信成功/失敗を正確に判定

1. submitボタン検出（type=submit, button text matching）
2. 送信前スクリーンショット
3. クリック → ページ遷移 or AJAX応答待ち
4. 成功判定:
   - サンキューページ検出（「ありがとう」「送信完了」「Thank you」）
   - URLパス変化（/thanks, /complete）
   - 同一ページの成功メッセージDOM出現
5. 失敗判定: バリデーションエラー表示、タイムアウト
6. 送信後スクリーンショット
7. 結果JSON出力 → sales-ai へレポート

### Phase 6: キュー統合 + バッチ実行
**目標**: sales-aiとの連携完成

1. ジョブスキーマ定義（URL, プロフィール, メッセージ, priority）
2. JSONファイルキュー（`queue/pending/` → `results/completed/`）
3. 並列実行（configurable concurrency, default=3）
4. リトライロジック（最大3回、exponential backoff）
5. 日次レポート生成（成功/失敗/スキップ集計）
6. 将来: Redis Queue + Worker プロセス化

## ジョブスキーマ

```json
{
  "job_id": "lead_001_20260504",
  "url": "https://example.co.jp/contact",
  "profile": {
    "company_name": "株式会社サンプル",
    "name": "山田 太郎",
    "email": "taro@example.com",
    "phone": "03-XXXX-XXXX",
    "department": "代表",
    "message": "貴社のWebサイトを拝見し、AI検索対策のご提案をさせていただきたく..."
  },
  "options": {
    "captcha_solve": true,
    "max_retries": 3,
    "screenshot": true,
    "dry_run": false
  },
  "created_at": "2026-05-04T10:00:00+09:00"
}
```

## 結果スキーマ

```json
{
  "job_id": "lead_001_20260504",
  "status": "success|failed|captcha_blocked|form_not_found|skipped",
  "url": "https://example.co.jp/contact",
  "fields_filled": 5,
  "fields_total": 7,
  "fields_skipped": ["captcha", "file_upload"],
  "screenshot_before": "results/lead_001_before.png",
  "screenshot_after": "results/lead_001_after.png",
  "error": null,
  "completed_at": "2026-05-04T10:02:15+09:00"
}
```

## 技術スタック

| レイヤー | 技術 | 理由 |
|---|---|---|
| ブラウザ自動化 | **Playwright (Python)** | Chromium/Firefox/WebKit対応、async、stealth plugin |
| LLM | **Claude API** (Haiku) | フィールドマッピングは軽量タスク、コスト最適 |
| スキーマ | **Pydantic v2** | ジョブ/結果のバリデーション |
| キュー | JSONファイル → **Redis (将来)** | 段階的に複雑化 |
| CAPTCHA | **2Captcha API** | reCAPTCHA v2対応、安価 |
| コンテナ | **Docker** | ヘッドレスChrome環境の再現性 |
| CI | **GitHub Actions** | テスト + Lint |

## sales-ai との接続点

```python
# sales-ai側: ジョブ投入
# scripts/submit_to_form_bot.py
import json
from pathlib import Path

FORM_BOT_QUEUE = Path("../sales-form-bot/queue/pending/")

def enqueue_form_job(lead: dict, message: str):
    job = {
        "job_id": f"{lead['id']}_{date}",
        "url": lead["contact_form_url"],
        "profile": {
            "company_name": "株式会社サンプル",
            "name": "山田 太郎",
            "email": "taro@example.com",
            "message": message,
        },
        "options": {"captcha_solve": True, "screenshot": True}
    }
    (FORM_BOT_QUEUE / f"{job['job_id']}.json").write_text(
        json.dumps(job, ensure_ascii=False, indent=2)
    )
```

## リスク & 対策

| リスク | 対策 |
|---|---|
| フォーム構造が多様すぎて検出率低い | 日本企業はCF7/WPForms率高い。特化パーサー優先 |
| CAPTCHA突破率が低い | 突破不能はスキップ、メール送信にフォールバック |
| アンチbot検出 | ヒューマニゼーション + residential proxy（将来） |
| 送信成功の誤判定 | スクリーンショット + DOM解析のダブルチェック |
| 法的リスク | 1日あたり送信上限（10件/日）、オプトアウト対応 |

## MVP完了の定義

- [ ] URLを渡すとフォームフィールドをJSON抽出できる
- [ ] LLMがフィールドとプロフィールデータを自動マッピングする
- [ ] 日本語のContact Form 7フォームに自動入力・送信できる
- [ ] 送信成功/失敗をスクリーンショット付きで判定できる
- [ ] sales-aiからジョブJSON投入 → 結果JSON返却の一連フローが動く
