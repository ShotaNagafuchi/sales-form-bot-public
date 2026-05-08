from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    TEXT = "text"
    EMAIL = "email"
    TEL = "tel"
    URL = "url"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    HIDDEN = "hidden"
    FILE = "file"
    NUMBER = "number"
    DATE = "date"
    PASSWORD = "password"
    UNKNOWN = "unknown"


class FormField(BaseModel):
    name: str = ""
    field_type: FieldType = FieldType.TEXT
    label: str = ""
    placeholder: str = ""
    required: bool = False
    options: list[str] = Field(default_factory=list)
    selector: str = ""
    attributes: dict[str, str] = Field(default_factory=dict)


class FormType(str, Enum):
    GENERIC = "generic"
    CONTACT_FORM_7 = "contact_form_7"
    WPFORMS = "wpforms"
    GOOGLE_FORM = "google_form"


class DetectedForm(BaseModel):
    url: str
    form_type: FormType = FormType.GENERIC
    fields: list[FormField] = Field(default_factory=list)
    submit_selector: str = ""
    form_selector: str = ""
    action: str = ""
    method: str = "POST"
