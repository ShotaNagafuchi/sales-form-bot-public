"""Validate mapping results before filling."""

from __future__ import annotations

from dataclasses import dataclass

from src.detector.models import DetectedForm, FieldType
from src.mapper.field_mapper import FieldMapping, MappingResult
from src.mapper.normalizer import normalize_value


@dataclass(frozen=True)
class ValidatedMapping:
    field_name: str
    field_selector: str
    value: str
    field_type: FieldType
    normalized_value: str


@dataclass(frozen=True)
class ValidationResult:
    valid_mappings: list[ValidatedMapping]
    skipped_fields: list[str]
    warnings: list[str]
    ready_to_fill: bool


def validate_mappings(
    mapping_result: MappingResult,
    form: DetectedForm,
    confidence_threshold: float = 0.6,
) -> ValidationResult:
    """Validate and normalize all field mappings.

    - Skips unmapped fields (value=None)
    - Skips low-confidence mappings below threshold
    - Normalizes values by field type
    - Checks that required fields have mappings
    """
    field_lookup = {f.name: f for f in form.fields}
    valid: list[ValidatedMapping] = []
    skipped: list[str] = []
    warnings: list[str] = []

    for m in mapping_result.mappings:
        form_field = field_lookup.get(m.field_name)
        if form_field is None:
            skipped.append(m.field_name)
            continue

        if m.value is None:
            skipped.append(m.field_name)
            continue

        if m.confidence < confidence_threshold:
            skipped.append(m.field_name)
            warnings.append(
                f"Low confidence ({m.confidence:.2f}) for '{m.field_name}': {m.reason}"
            )
            continue

        normalized = normalize_value(m.value, form_field.field_type)

        valid.append(
            ValidatedMapping(
                field_name=m.field_name,
                field_selector=form_field.selector or m.field_selector,
                value=m.value,
                field_type=form_field.field_type,
                normalized_value=normalized,
            )
        )

    # Check required fields
    for f in form.fields:
        if f.required and f.name in [s for s in skipped]:
            warnings.append(f"Required field '{f.name}' ({f.label}) has no valid mapping")

    required_missing = any(
        f.required and f.name not in [v.field_name for v in valid]
        for f in form.fields
    )

    return ValidationResult(
        valid_mappings=valid,
        skipped_fields=skipped,
        warnings=warnings,
        ready_to_fill=not required_missing,
    )
