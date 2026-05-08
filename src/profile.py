"""Load sender profile from profiles/default.json."""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "profiles" / "default.json"


def load_profile(path: str | None = None) -> dict[str, str]:
    """Load profile from a JSON file. Falls back to profiles/default.json."""
    p = Path(path) if path else _DEFAULT_PROFILE_PATH
    return json.loads(p.read_text(encoding="utf-8"))
