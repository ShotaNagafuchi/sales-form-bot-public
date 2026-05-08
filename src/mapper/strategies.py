"""Multiple form mapping strategies for A/B comparison.

Strategy A: Current rule-based (pattern matching on label/name/placeholder)
Strategy B: name-attribute-only selectors (avoids broken ID selectors)
Strategy C: label/placeholder semantic matching (resilient to bad markup)
Strategy D: Sequential type-based filling (no parser dependency)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.detector.models import DetectedForm, FieldType, FormField
from src.mapper.field_mapper import (
    FieldMapping,
    MappingResult,
    _match_select_option,
    _pick_select_fallback,
)


@dataclass(frozen=True)
class Strategy:
    name: str
    description: str


STRATEGY_A = Strategy("rule_based", "Pattern match on label/name/placeholder with ID selectors")
STRATEGY_B = Strategy("name_attr", "Use [name] selectors only, skip fields without name")
STRATEGY_C = Strategy("semantic", "Match by label/placeholder text semantics, flexible selectors")
STRATEGY_D = Strategy("sequential", "Fill fields top-to-bottom by type inference")

STRATEGY_HYBRID = Strategy("hybrid", "Rule-based first, sequential fallback for unmapped fields")

ALL_STRATEGIES = [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D, STRATEGY_HYBRID]


# Shared pattern definitions
_FIELD_PATTERNS: dict[str, list[str]] = {
    "company_name": ["会社", "社名", "御社", "company", "organization", "corp", "貴社", "勤務先"],
    "name": ["名前", "氏名", "お名前", "your-name", "fullname", "担当者"],
    "name_sei": ["姓", "last.?name", "sei"],
    "name_mei": ["名(?!前)", "first.?name", "mei"],
    "furigana": ["ふりがな", "フリガナ", "かな", "カナ", "kana", "furigana", "読み"],
    "furigana_sei": ["せい", "セイ"],
    "furigana_mei": ["めい", "メイ"],
    "email": ["メール", "mail", "email", "e-mail"],
    "phone": ["電話", "tel", "phone", "連絡先", "携帯"],
    "zip": ["郵便", "zip", "postal", "〒"],
    "address": ["住所", "address", "所在地", "都道府県"],
    "department": ["部署", "所属", "department", "division", "部門"],
    "position": ["役職", "position", "title", "肩書"],
    "url": ["ホームページ", "url", "website", "サイト"],
    "message": ["内容", "メッセージ", "message", "要件", "用件", "body", "inquiry",
                "問い合わせ", "ご相談", "詳細", "備考", "自由記入"],
}


def _match_field_to_profile_key(searchable: str) -> tuple[str | None, float]:
    """Match a searchable text against profile patterns. Returns (key, confidence)."""
    for profile_key, patterns in _FIELD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, searchable, re.IGNORECASE):
                return profile_key, 0.85
    return None, 0.0


def _build_selector_for_field(field: FormField, strategy: Strategy) -> str:
    """Build an appropriate CSS selector based on strategy."""
    if strategy == STRATEGY_B:
        # Only use name attribute
        if field.name:
            tag = "input"
            if field.field_type == FieldType.TEXTAREA:
                tag = "textarea"
            elif field.field_type == FieldType.SELECT:
                tag = "select"
            return f'{tag}[name="{field.name}"]'
        return ""

    # For strategies A, C, D: use existing selector but fix if invalid
    selector = field.selector
    if selector and selector.startswith("#"):
        id_part = selector[1:]
        # Fix invalid CSS selectors (numeric start, special chars)
        if id_part and (id_part[0].isdigit() or not _is_valid_css_id(id_part)):
            selector = f'[id="{id_part}"]'

    if not selector and field.name:
        tag = "input"
        if field.field_type == FieldType.TEXTAREA:
            tag = "textarea"
        elif field.field_type == FieldType.SELECT:
            tag = "select"
        selector = f'{tag}[name="{field.name}"]'

    return selector


def _is_valid_css_id(s: str) -> bool:
    """Check if string is a valid CSS identifier."""
    return bool(re.match(r'^[a-zA-Z_][a-zA-Z0-9_-]*$', s))


def map_strategy_a(form: DetectedForm, profile: dict[str, str]) -> MappingResult:
    """Strategy A: Current rule-based approach with fixed selectors."""
    return _map_with_patterns(form, profile, STRATEGY_A)


def map_strategy_b(form: DetectedForm, profile: dict[str, str]) -> MappingResult:
    """Strategy B: name-attribute-only selectors."""
    return _map_with_patterns(form, profile, STRATEGY_B)


def map_strategy_c(form: DetectedForm, profile: dict[str, str]) -> MappingResult:
    """Strategy C: Semantic matching — uses label+placeholder as primary signal."""
    return _map_with_patterns(form, profile, STRATEGY_C)


def map_strategy_d(form: DetectedForm, profile: dict[str, str]) -> MappingResult:
    """Strategy D: Sequential type-based filling.

    Ignores labels entirely. Fills fields top-to-bottom based on field type:
    - First email field → email
    - First tel field → phone
    - First textarea → message
    - Text fields → fill in order: company, name, furigana, department, address
    """
    text_values = [
        ("company_name", profile.get("company_name", "")),
        ("name", profile.get("name", "")),
        ("furigana", profile.get("furigana", "")),
        ("department", profile.get("department", "")),
        ("zip", profile.get("zip", "")),
        ("address", profile.get("address", "")),
        ("position", profile.get("position", "")),
        ("url", profile.get("url", "")),
    ]
    text_idx = 0

    mappings: list[FieldMapping] = []
    email_used = False
    phone_used = False
    message_used = False

    for field in form.fields:
        selector = _build_selector_for_field(field, STRATEGY_D)
        if not selector:
            mappings.append(FieldMapping(field.name, selector, None, 0.0, "No selector"))
            continue

        value: str | None = None
        confidence = 0.7

        match field.field_type:
            case FieldType.EMAIL:
                if not email_used:
                    value = profile.get("email", "")
                    email_used = True
                    confidence = 0.95
            case FieldType.TEL:
                if not phone_used:
                    value = profile.get("phone", "")
                    phone_used = True
                    confidence = 0.95
            case FieldType.TEXTAREA:
                if not message_used:
                    value = profile.get("message", "")
                    message_used = True
                    confidence = 0.9
            case FieldType.SELECT:
                if field.options:
                    value = _pick_select_fallback(field.options)
                    confidence = 0.6
            case FieldType.CHECKBOX:
                checkbox_text = (field.label + field.name).lower()
                if any(t in checkbox_text for t in ["同意", "プライバシー", "privacy", "agree", "規約"]):
                    value = "agree"
                    confidence = 0.9
            case FieldType.TEXT | FieldType.URL | FieldType.NUMBER:
                if text_idx < len(text_values):
                    _, value = text_values[text_idx]
                    text_idx += 1
                    confidence = 0.6
            case _:
                pass

        mappings.append(FieldMapping(
            field_name=field.name,
            field_selector=selector,
            value=value,
            confidence=confidence,
            reason=f"Sequential type-based ({field.field_type.value})",
        ))

    unmapped = [m.field_name for m in mappings if m.value is None]
    low_conf = [m.field_name for m in mappings if m.value and m.confidence < 0.6]
    return MappingResult(mappings=mappings, unmapped_fields=unmapped, low_confidence_fields=low_conf)


def _map_with_patterns(
    form: DetectedForm, profile: dict[str, str], strategy: Strategy
) -> MappingResult:
    """Shared pattern-matching logic for strategies A, B, C."""
    mappings: list[FieldMapping] = []

    for field in form.fields:
        selector = _build_selector_for_field(field, strategy)
        if not selector:
            mappings.append(FieldMapping(field.name, "", None, 0.0, "No usable selector"))
            continue

        # Build search text — strategy C emphasizes label/placeholder
        if strategy == STRATEGY_C:
            searchable = f"{field.label} {field.placeholder}".lower()
        else:
            searchable = f"{field.label} {field.name} {field.placeholder}".lower()

        # Handle checkboxes
        if field.field_type == FieldType.CHECKBOX:
            checkbox_terms = ["同意", "プライバシー", "privacy", "agree", "terms", "規約"]
            if any(t in searchable for t in checkbox_terms):
                mappings.append(FieldMapping(
                    field.name, selector, "agree", 0.9, "Privacy/terms checkbox",
                ))
                continue

        matched_key, confidence = _match_field_to_profile_key(searchable)

        if matched_key and matched_key in profile:
            value = profile[matched_key]

            if field.options and value:
                matched_opt = _match_select_option(value, field.options)
                if matched_opt:
                    value = matched_opt
                else:
                    value = _pick_select_fallback(field.options)
                    confidence = 0.65

            mappings.append(FieldMapping(
                field.name, selector, value, confidence,
                f"Matched '{matched_key}' via {strategy.name}",
            ))
        elif field.field_type == FieldType.SELECT and field.options:
            fallback = _pick_select_fallback(field.options)
            mappings.append(FieldMapping(
                field.name, selector, fallback, 0.6,
                "Select fallback: safe default option",
            ))
        else:
            mappings.append(FieldMapping(
                field.name, selector, None, 0.0, "No matching profile field",
            ))

    unmapped = [m.field_name for m in mappings if m.value is None]
    low_conf = [m.field_name for m in mappings if m.value and m.confidence < 0.6]
    return MappingResult(mappings=mappings, unmapped_fields=unmapped, low_confidence_fields=low_conf)


def map_strategy_hybrid(form: DetectedForm, profile: dict[str, str]) -> MappingResult:
    """Strategy Hybrid: Rule-based first (A), then sequential (D) fills any gaps.

    Best of both worlds — pattern matching provides accurate mapping where labels
    are clear, sequential type inference fills the rest.
    """
    # Step 1: Run rule-based mapping
    rule_result = map_strategy_a(form, profile)

    # Step 2: Run sequential mapping
    seq_result = map_strategy_d(form, profile)

    # Step 3: Merge — prefer rule-based where it has a value, fill gaps from sequential
    merged: list[FieldMapping] = []
    seq_by_name = {m.field_name: m for m in seq_result.mappings}

    for rule_m in rule_result.mappings:
        if rule_m.value is not None and rule_m.confidence >= 0.6:
            # Rule-based has a good match — use it
            merged.append(rule_m)
        elif rule_m.field_name in seq_by_name:
            seq_m = seq_by_name[rule_m.field_name]
            if seq_m.value is not None:
                # Sequential has a value — use it but mark as fallback
                merged.append(FieldMapping(
                    field_name=seq_m.field_name,
                    field_selector=rule_m.field_selector or seq_m.field_selector,
                    value=seq_m.value,
                    confidence=min(seq_m.confidence, 0.7),
                    reason=f"Hybrid: sequential fallback ({seq_m.reason})",
                ))
            else:
                merged.append(rule_m)
        else:
            merged.append(rule_m)

    unmapped = [m.field_name for m in merged if m.value is None]
    low_conf = [m.field_name for m in merged if m.value and m.confidence < 0.6]
    return MappingResult(mappings=merged, unmapped_fields=unmapped, low_confidence_fields=low_conf)
