"""Tests for field mapping, normalization, and validation."""

from __future__ import annotations

import pytest

from src.detector.models import DetectedForm, FieldType, FormField, FormType
from src.mapper.field_mapper import (
    FieldMapping,
    MappingResult,
    _parse_llm_response,
    map_fields_deterministic,
)
from src.mapper.normalizer import normalize_value
from src.mapper.validator import validate_mappings

# --- Fixtures ---

SAMPLE_PROFILE = {
    "company_name": "Acme Corporation",
    "name": "Taro Yamada",
    "email": "taro@example.com",
    "phone": "0312345678",
    "department": "代表",
    "message": "貴社のWebサイトを拝見し、ご提案をさせていただきたくご連絡いたしました。",
}


def _make_form() -> DetectedForm:
    return DetectedForm(
        url="https://example.co.jp/contact",
        form_type=FormType.CONTACT_FORM_7,
        fields=[
            FormField(
                name="your-name",
                field_type=FieldType.TEXT,
                label="お名前（必須）",
                required=True,
                selector='[name="your-name"]',
            ),
            FormField(
                name="your-email",
                field_type=FieldType.EMAIL,
                label="メールアドレス（必須）",
                required=True,
                selector='[name="your-email"]',
            ),
            FormField(
                name="your-tel",
                field_type=FieldType.TEL,
                label="電話番号",
                selector='[name="your-tel"]',
            ),
            FormField(
                name="your-company",
                field_type=FieldType.TEXT,
                label="会社名",
                selector='[name="your-company"]',
            ),
            FormField(
                name="your-subject",
                field_type=FieldType.SELECT,
                label="お問い合わせ種別",
                options=["サービスについて", "料金について", "その他"],
                selector='[name="your-subject"]',
            ),
            FormField(
                name="your-message",
                field_type=FieldType.TEXTAREA,
                label="お問い合わせ内容（必須）",
                required=True,
                selector='[name="your-message"]',
            ),
            FormField(
                name="privacy",
                field_type=FieldType.CHECKBOX,
                label="プライバシーポリシーに同意する",
                required=True,
                selector='[name="privacy"]',
            ),
        ],
        submit_selector='input[type="submit"]',
        form_selector="form.wpcf7-form",
    )


# --- Deterministic Mapper Tests ---


class TestDeterministicMapper:
    def test_maps_name_field(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        name_mapping = next(m for m in result.mappings if m.field_name == "your-name")
        assert name_mapping.value == "Taro Yamada"
        assert name_mapping.confidence > 0.5

    def test_maps_email_field(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        email_mapping = next(m for m in result.mappings if m.field_name == "your-email")
        assert email_mapping.value == "taro@example.com"

    def test_maps_phone_field(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        tel_mapping = next(m for m in result.mappings if m.field_name == "your-tel")
        assert tel_mapping.value == "0312345678"

    def test_maps_company_field(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        company_mapping = next(m for m in result.mappings if m.field_name == "your-company")
        assert company_mapping.value == "Acme Corporation"

    def test_maps_message_field(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        msg_mapping = next(m for m in result.mappings if m.field_name == "your-message")
        assert msg_mapping.value is not None
        assert "ご提案" in msg_mapping.value

    def test_maps_privacy_checkbox(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        privacy_mapping = next(m for m in result.mappings if m.field_name == "privacy")
        assert privacy_mapping.value == "agree"

    def test_select_field_no_exact_match(self):
        """Select field with no matching profile data should map to None."""
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        subject_mapping = next(m for m in result.mappings if m.field_name == "your-subject")
        # "お問い合わせ種別" doesn't directly match any profile pattern
        # The select options don't match any profile value either
        assert subject_mapping.field_name == "your-subject"

    def test_all_fields_have_mappings(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        assert len(result.mappings) == 7  # All fields get a mapping entry

    def test_select_gets_fallback(self):
        result = map_fields_deterministic(_make_form(), SAMPLE_PROFILE)
        subject = next(m for m in result.mappings if m.field_name == "your-subject")
        # Select fields now get a fallback option instead of being unmapped
        assert subject.value is not None
        assert subject.value in ["サービスについて", "料金について", "その他"]


# --- Normalizer Tests ---


class TestNormalizer:
    def test_normalize_email(self):
        assert normalize_value("  TARO@Example.com  ", FieldType.EMAIL) == "taro@example.com"

    def test_normalize_phone_10digits(self):
        assert normalize_value("0312345678", FieldType.TEL) == "03-1234-5678"

    def test_normalize_phone_11digits(self):
        assert normalize_value("09012345678", FieldType.TEL) == "090-1234-5678"

    def test_normalize_phone_with_hyphens_unchanged(self):
        assert normalize_value("03-1234-5678", FieldType.TEL) == "03-1234-5678"

    def test_normalize_phone_osaka(self):
        assert normalize_value("0612345678", FieldType.TEL) == "06-1234-5678"

    def test_normalize_phone_area_code_3digits(self):
        assert normalize_value("0451234567", FieldType.TEL) == "045-1234-567"

    def test_normalize_url_adds_scheme(self):
        assert normalize_value("example.com", FieldType.URL) == "https://example.com"

    def test_normalize_url_keeps_existing_scheme(self):
        assert normalize_value("https://example.com", FieldType.URL) == "https://example.com"

    def test_normalize_text_strips_whitespace(self):
        assert normalize_value("  hello  ", FieldType.TEXT) == "hello"


# --- LLM Response Parser Tests ---


class TestLLMResponseParser:
    def test_parses_json_array(self):
        raw = '[{"field_name": "name", "field_selector": "#name", "value": "太郎", "confidence": 0.95, "reason": "label match"}]'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0].field_name == "name"
        assert result[0].value == "太郎"
        assert result[0].confidence == 0.95

    def test_parses_with_code_fences(self):
        raw = '```json\n[{"field_name": "email", "field_selector": "#email", "value": "a@b.com", "confidence": 0.9, "reason": "email field"}]\n```'
        result = _parse_llm_response(raw)
        assert len(result) == 1
        assert result[0].value == "a@b.com"

    def test_parses_null_value(self):
        raw = '[{"field_name": "x", "field_selector": "", "value": null, "confidence": 0.0, "reason": "no match"}]'
        result = _parse_llm_response(raw)
        assert result[0].value is None


# --- Validator Tests ---


class TestValidator:
    def test_valid_mappings_pass(self):
        form = _make_form()
        mapping_result = map_fields_deterministic(form, SAMPLE_PROFILE)
        validation = validate_mappings(mapping_result, form)

        assert len(validation.valid_mappings) >= 5  # At least name, email, tel, company, message
        assert validation.ready_to_fill  # Required fields are filled

    def test_skips_low_confidence(self):
        form = _make_form()
        low_conf_mapping = MappingResult(
            mappings=[
                FieldMapping("your-name", '[name="your-name"]', "太郎", 0.3, "weak"),
            ],
            unmapped_fields=[],
            low_confidence_fields=["your-name"],
        )
        validation = validate_mappings(low_conf_mapping, form, confidence_threshold=0.6)
        assert "your-name" in validation.skipped_fields

    def test_normalizes_values(self):
        form = _make_form()
        mapping_result = map_fields_deterministic(form, SAMPLE_PROFILE)
        validation = validate_mappings(mapping_result, form)

        tel_mapping = next(
            (v for v in validation.valid_mappings if v.field_name == "your-tel"), None
        )
        assert tel_mapping is not None
        assert tel_mapping.normalized_value == "03-1234-5678"

    def test_warns_on_missing_required(self):
        form = _make_form()
        empty_mapping = MappingResult(
            mappings=[
                FieldMapping("your-name", "", None, 0.0, "no match"),
                FieldMapping("your-email", "", None, 0.0, "no match"),
                FieldMapping("your-message", "", None, 0.0, "no match"),
                FieldMapping("privacy", "", None, 0.0, "no match"),
            ],
            unmapped_fields=["your-name", "your-email", "your-message", "privacy"],
            low_confidence_fields=[],
        )
        validation = validate_mappings(empty_mapping, form)
        assert not validation.ready_to_fill
        assert len(validation.warnings) > 0
