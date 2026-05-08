"""Tests for form filling engine."""

from __future__ import annotations

import pytest

from src.detector.models import FieldType
from src.filler.engine import fill_form
from src.mapper.validator import ValidatedMapping
from tests.conftest import fixture_url


def _make_mappings() -> list[ValidatedMapping]:
    return [
        ValidatedMapping(
            field_name="name",
            field_selector="#name",
            value="Taro Yamada",
            field_type=FieldType.TEXT,
            normalized_value="Taro Yamada",
        ),
        ValidatedMapping(
            field_name="email",
            field_selector="#email",
            value="taro@example.com",
            field_type=FieldType.EMAIL,
            normalized_value="taro@example.com",
        ),
        ValidatedMapping(
            field_name="phone",
            field_selector="#phone",
            value="0312345678",
            field_type=FieldType.TEL,
            normalized_value="03-1234-5678",
        ),
        ValidatedMapping(
            field_name="company",
            field_selector="#company",
            value="Acme Corporation",
            field_type=FieldType.TEXT,
            normalized_value="Acme Corporation",
        ),
        ValidatedMapping(
            field_name="subject",
            field_selector="#subject",
            value="お見積もり",
            field_type=FieldType.SELECT,
            normalized_value="お見積もり",
        ),
        ValidatedMapping(
            field_name="message",
            field_selector="#message",
            value="ご提案をさせていただきたくご連絡いたしました。",
            field_type=FieldType.TEXTAREA,
            normalized_value="ご提案をさせていただきたくご連絡いたしました。",
        ),
        ValidatedMapping(
            field_name="privacy",
            field_selector="#privacy",
            value="agree",
            field_type=FieldType.CHECKBOX,
            normalized_value="agree",
        ),
    ]


@pytest.mark.asyncio
class TestFormFilling:
    async def test_fills_all_fields(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        mappings = _make_mappings()
        result = await fill_form(page, mappings, humanize=False)

        assert len(result.filled) == 7
        assert len(result.errors) == 0

    async def test_text_input_values(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        await fill_form(page, _make_mappings(), humanize=False)

        assert await page.input_value("#name") == "Taro Yamada"
        assert await page.input_value("#email") == "taro@example.com"
        assert await page.input_value("#phone") == "03-1234-5678"
        assert await page.input_value("#company") == "Acme Corporation"

    async def test_textarea_value(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        await fill_form(page, _make_mappings(), humanize=False)

        value = await page.input_value("#message")
        assert "ご提案" in value

    async def test_select_value(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        await fill_form(page, _make_mappings(), humanize=False)

        # Check the selected option text
        selected = await page.evaluate(
            '() => document.querySelector("#subject").selectedOptions[0].text'
        )
        assert selected == "お見積もり"

    async def test_checkbox_checked(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        await fill_form(page, _make_mappings(), humanize=False)

        assert await page.is_checked("#privacy") is True

    async def test_skips_missing_selector(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        bad_mapping = [
            ValidatedMapping(
                field_name="nonexistent",
                field_selector="#does-not-exist",
                value="test",
                field_type=FieldType.TEXT,
                normalized_value="test",
            ),
        ]
        result = await fill_form(page, bad_mapping, humanize=False)
        assert "nonexistent" in result.skipped

    async def test_skips_empty_selector(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        bad_mapping = [
            ValidatedMapping(
                field_name="empty",
                field_selector="",
                value="test",
                field_type=FieldType.TEXT,
                normalized_value="test",
            ),
        ]
        result = await fill_form(page, bad_mapping, humanize=False)
        assert "empty" in result.skipped

    async def test_humanized_fill(self, page):
        """Humanized fill should produce the same result (just slower)."""
        url = fixture_url("generic_contact.html")
        await page.goto(url)

        # Only fill 2 fields to keep test fast
        mappings = _make_mappings()[:2]
        result = await fill_form(page, mappings, humanize=True)

        assert len(result.filled) == 2
        assert await page.input_value("#name") == "Taro Yamada"
        assert await page.input_value("#email") == "taro@example.com"


@pytest.mark.asyncio
class TestFormFillingCF7:
    async def test_fills_cf7_form(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)

        mappings = [
            ValidatedMapping(
                field_name="your-name",
                field_selector='[name="your-name"]',
                value="Taro Yamada",
                field_type=FieldType.TEXT,
                normalized_value="Taro Yamada",
            ),
            ValidatedMapping(
                field_name="your-email",
                field_selector='[name="your-email"]',
                value="taro@example.com",
                field_type=FieldType.EMAIL,
                normalized_value="taro@example.com",
            ),
            ValidatedMapping(
                field_name="your-message",
                field_selector='[name="your-message"]',
                value="テストメッセージ",
                field_type=FieldType.TEXTAREA,
                normalized_value="テストメッセージ",
            ),
        ]
        result = await fill_form(page, mappings, humanize=False)

        assert len(result.filled) == 3
        assert await page.input_value('[name="your-name"]') == "Taro Yamada"
        assert await page.input_value('[name="your-email"]') == "taro@example.com"
        assert await page.input_value('[name="your-message"]') == "テストメッセージ"
