"""Tests for form detection and field extraction."""

from __future__ import annotations

import pytest

from src.detector.extractor import extract_forms
from src.detector.models import FieldType, FormType
from src.detector.parsers.wordpress import parse_cf7, parse_wpforms
from tests.conftest import fixture_url


@pytest.mark.asyncio
class TestGenericFormExtraction:
    async def test_detects_form(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)

        assert len(forms) == 1
        form = forms[0]
        assert form.form_type == FormType.GENERIC

    async def test_extracts_all_visible_fields(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        form = forms[0]

        # name, email, phone, company, subject(select), message(textarea), privacy(checkbox)
        assert len(form.fields) == 7

    async def test_field_types(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        fields = forms[0].fields

        type_map = {f.name: f.field_type for f in fields}
        assert type_map["name"] == FieldType.TEXT
        assert type_map["email"] == FieldType.EMAIL
        assert type_map["phone"] == FieldType.TEL
        assert type_map["subject"] == FieldType.SELECT
        assert type_map["message"] == FieldType.TEXTAREA
        assert type_map["privacy"] == FieldType.CHECKBOX

    async def test_labels_extracted(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        fields = forms[0].fields

        label_map = {f.name: f.label for f in fields}
        assert "お名前" in label_map["name"]
        assert "メールアドレス" in label_map["email"]

    async def test_required_fields(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        fields = forms[0].fields

        required_map = {f.name: f.required for f in fields}
        assert required_map["name"] is True
        assert required_map["email"] is True
        assert required_map["phone"] is False

    async def test_select_options(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        fields = forms[0].fields

        subject = next(f for f in fields if f.name == "subject")
        assert len(subject.options) == 3
        assert "お見積もり" in subject.options

    async def test_submit_selector(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        assert forms[0].submit_selector != ""

    async def test_selectors_present(self, page):
        url = fixture_url("generic_contact.html")
        await page.goto(url)
        forms = await extract_forms(page, url)
        for field in forms[0].fields:
            assert field.selector != "", f"Missing selector for field: {field.name}"


@pytest.mark.asyncio
class TestCF7Extraction:
    async def test_detects_cf7_form(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)
        forms = await parse_cf7(page, url)

        assert len(forms) == 1
        assert forms[0].form_type == FormType.CONTACT_FORM_7

    async def test_extracts_cf7_fields(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)
        forms = await parse_cf7(page, url)
        fields = forms[0].fields

        # name, email, tel, company, subject(select), message(textarea)
        assert len(fields) == 6

    async def test_cf7_field_types(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)
        forms = await parse_cf7(page, url)
        fields = forms[0].fields

        type_map = {f.name: f.field_type for f in fields}
        assert type_map["your-email"] == FieldType.EMAIL
        assert type_map["your-tel"] == FieldType.TEL
        assert type_map["your-message"] == FieldType.TEXTAREA
        assert type_map["your-subject"] == FieldType.SELECT

    async def test_cf7_required(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)
        forms = await parse_cf7(page, url)
        fields = forms[0].fields

        required_map = {f.name: f.required for f in fields}
        assert required_map["your-name"] is True
        assert required_map["your-email"] is True
        assert required_map["your-tel"] is False

    async def test_cf7_labels(self, page):
        url = fixture_url("cf7_contact.html")
        await page.goto(url)
        forms = await parse_cf7(page, url)
        fields = forms[0].fields

        label_map = {f.name: f.label for f in fields}
        assert "お名前" in label_map["your-name"]
        assert "メールアドレス" in label_map["your-email"]


@pytest.mark.asyncio
class TestWPFormsExtraction:
    async def test_detects_wpforms(self, page):
        url = fixture_url("wpforms_contact.html")
        await page.goto(url)
        forms = await parse_wpforms(page, url)

        assert len(forms) == 1
        assert forms[0].form_type == FormType.WPFORMS

    async def test_extracts_wpforms_fields(self, page):
        url = fixture_url("wpforms_contact.html")
        await page.goto(url)
        forms = await parse_wpforms(page, url)
        fields = forms[0].fields

        # name, email, phone, message
        assert len(fields) == 4

    async def test_wpforms_required(self, page):
        url = fixture_url("wpforms_contact.html")
        await page.goto(url)
        forms = await parse_wpforms(page, url)
        fields = forms[0].fields

        required_names = [f.name for f in fields if f.required]
        assert len(required_names) >= 2  # At least name and email
