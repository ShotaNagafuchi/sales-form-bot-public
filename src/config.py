from __future__ import annotations

import os
from dataclasses import dataclass, field


_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool = True
    timeout_ms: int = 30_000
    user_agent: str = _DEFAULT_UA


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    max_tokens: int = 1024


@dataclass(frozen=True)
class QueueConfig:
    pending_dir: str = "queue/pending"
    completed_dir: str = "results/completed"
    concurrency: int = 3
    max_retries: int = 3


@dataclass(frozen=True)
class Config:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    queue: QueueConfig = field(default_factory=QueueConfig)
    daily_limit: int = 10
    screenshot_dir: str = "results/screenshots"
