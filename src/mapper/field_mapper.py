"""LLM-based semantic field mapping: form fields → profile data."""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from src.config import LLMConfig
from src.detector.models import DetectedForm, FormField

_SYSTEM_PROMPT = """\
You are a form field mapper. Given a list of form fields (with labels, names, types, and options) \
and a sender profile, map each field to the correct profile value.

Rules:
- Map fields based on semantic meaning of labels/names/placeholders (e.g. "御社名" → company_name, "ご用件" → message)
- For select/dropdown fields, pick the best matching option from the available choices. If no option fits, use null.
- For checkbox fields about privacy/terms/agreement, set value to "agree" (meaning: check it).
- For radio fields, pick the most appropriate option or null.
- If a field clearly cannot be mapped to any profile data, set value to null.
- Assign a confidence score (0.0 to 1.0) for each mapping.

Respond with ONLY a JSON array. Each element:
{"field_name": "<name attr>", "field_selector": "<css selector>", "value": "<mapped value or null>", "confidence": <0.0-1.0>, "reason": "<brief reason>"}
"""


def _build_user_prompt(form: DetectedForm, profile: dict[str, str]) -> str:
    fields_desc = []
    for f in form.fields:
        desc = {
            "name": f.name,
            "type": f.field_type.value,
            "label": f.label,
            "placeholder": f.placeholder,
            "required": f.required,
            "selector": f.selector,
        }
        if f.options:
            desc["options"] = f.options
        fields_desc.append(desc)

    return (
        f"## Form Fields\n```json\n{json.dumps(fields_desc, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## Sender Profile\n```json\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n```"
    )


@dataclass(frozen=True)
class FieldMapping:
    field_name: str
    field_selector: str
    value: str | None
    confidence: float
    reason: str


@dataclass(frozen=True)
class MappingResult:
    mappings: list[FieldMapping]
    unmapped_fields: list[str]
    low_confidence_fields: list[str]


def _parse_llm_response(raw: str) -> list[FieldMapping]:
    """Parse the JSON array from LLM response."""
    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    items = json.loads(text)
    mappings = []
    for item in items:
        mappings.append(
            FieldMapping(
                field_name=item.get("field_name", ""),
                field_selector=item.get("field_selector", ""),
                value=item.get("value"),
                confidence=float(item.get("confidence", 0.0)),
                reason=item.get("reason", ""),
            )
        )
    return mappings


async def map_fields(
    form: DetectedForm,
    profile: dict[str, str],
    config: LLMConfig | None = None,
    confidence_threshold: float = 0.6,
) -> MappingResult:
    """Use LLM to map form fields to profile data.

    Returns MappingResult with mappings, unmapped fields, and low-confidence fields.
    """
    cfg = config or LLMConfig()
    client = anthropic.AsyncAnthropic(api_key=cfg.api_key)

    user_prompt = _build_user_prompt(form, profile)

    response = await client.messages.create(
        model=cfg.model,
        max_tokens=cfg.max_tokens,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw_text = response.content[0].text
    mappings = _parse_llm_response(raw_text)

    unmapped = [m.field_name for m in mappings if m.value is None]
    low_conf = [
        m.field_name
        for m in mappings
        if m.value is not None and m.confidence < confidence_threshold
    ]

    return MappingResult(
        mappings=mappings,
        unmapped_fields=unmapped,
        low_confidence_fields=low_conf,
    )


def map_fields_deterministic(
    form: DetectedForm,
    profile: dict[str, str],
) -> MappingResult:
    """Rule-based fallback mapper (no LLM). Uses heuristic name/label matching.

    Useful for testing and as a fallback when LLM is unavailable.
    """
    mappings: list[FieldMapping] = []

    # Build lookup from common Japanese/English field indicators
    profile_patterns: dict[str, list[str]] = {
        "company_name": ["会社", "社名", "御社", "company", "organization", "corp", "貴社"],
        "name": ["名前", "氏名", "お名前", "your-name", "fullname", "name", "担当者"],
        "name_sei": ["姓", "last.?name", "sei"],
        "name_mei": ["名", "first.?name", "mei"],
        "furigana": ["ふりがな", "フリガナ", "かな", "カナ", "kana", "furigana", "読み"],
        "furigana_sei": ["せい", "セイ"],
        "furigana_mei": ["めい", "メイ"],
        "email": ["メール", "mail", "email", "e-mail"],
        "phone": ["電話", "tel", "phone", "連絡先"],
        "zip": ["郵便", "zip", "postal", "〒"],
        "address": ["住所", "address", "所在地"],
        "department": ["部署", "所属", "department", "division"],
        "position": ["役職", "position", "title"],
        "url": ["ホームページ", "url", "website", "サイト"],
        "message": ["内容", "メッセージ", "message", "要件", "用件", "body", "inquiry", "問い合わせ", "ご相談", "詳細"],
    }

    for field in form.fields:
        searchable = (field.label + field.name + field.placeholder).lower()
        matched_key: str | None = None
        confidence = 0.0

        for profile_key, patterns in profile_patterns.items():
            for pattern in patterns:
                if pattern.lower() in searchable:
                    matched_key = profile_key
                    confidence = 0.85
                    break
            if matched_key:
                break

        # Handle special field types
        if field.field_type.value == "checkbox" and matched_key is None:
            checkbox_terms = ["同意", "プライバシー", "privacy", "agree", "terms", "規約"]
            if any(t in searchable for t in checkbox_terms):
                mappings.append(
                    FieldMapping(
                        field_name=field.name,
                        field_selector=field.selector,
                        value="agree",
                        confidence=0.9,
                        reason="Privacy/terms checkbox",
                    )
                )
                continue

        if matched_key and matched_key in profile:
            value = profile[matched_key]

            # For select fields, try to find best option
            if field.options and value:
                matched_opt = _match_select_option(value, field.options)
                if matched_opt:
                    value = matched_opt
                else:
                    # Fallback: pick a safe default option
                    value = _pick_select_fallback(field.options)
                    confidence = 0.65  # Lower confidence for fallback

            mappings.append(
                FieldMapping(
                    field_name=field.name,
                    field_selector=field.selector,
                    value=value,
                    confidence=confidence,
                    reason=f"Matched '{matched_key}' by pattern in label/name",
                )
            )
        elif field.field_type.value == "select" and field.options:
            # Unmapped select: pick a safe fallback option
            fallback = _pick_select_fallback(field.options)
            mappings.append(
                FieldMapping(
                    field_name=field.name,
                    field_selector=field.selector,
                    value=fallback,
                    confidence=0.6,
                    reason="Select fallback: picked safe default option",
                )
            )
        else:
            mappings.append(
                FieldMapping(
                    field_name=field.name,
                    field_selector=field.selector,
                    value=None,
                    confidence=0.0,
                    reason="No matching profile field found",
                )
            )

    unmapped = [m.field_name for m in mappings if m.value is None]
    low_conf = [
        m.field_name
        for m in mappings
        if m.value is not None and m.confidence < 0.6
    ]

    return MappingResult(
        mappings=mappings,
        unmapped_fields=unmapped,
        low_confidence_fields=low_conf,
    )


def _match_select_option(value: str, options: list[str]) -> str | None:
    """Find the best matching option for a value using simple substring matching."""
    value_lower = value.lower()
    for opt in options:
        if value_lower in opt.lower() or opt.lower() in value_lower:
            return opt
    return None


def _pick_select_fallback(options: list[str]) -> str | None:
    """Pick a safe fallback option from a select field.

    Prefers: その他 > お問い合わせ > サービス > first option.
    """
    fallback_priorities = ["その他", "問い合わせ", "サービス", "相談", "other", "general", "inquiry"]
    for keyword in fallback_priorities:
        for opt in options:
            if keyword in opt.lower():
                return opt
    # Last resort: first option
    return options[0] if options else None
