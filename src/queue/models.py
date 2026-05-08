from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class JobOptions(BaseModel):
    captcha_solve: bool = True
    max_retries: int = 3
    screenshot: bool = True
    dry_run: bool = False


class JobProfile(BaseModel):
    company_name: str
    name: str
    name_sei: str = ""
    name_mei: str = ""
    furigana: str = ""
    furigana_sei: str = ""
    furigana_mei: str = ""
    email: str
    phone: str = ""
    zip: str = ""
    address: str = ""
    department: str = ""
    position: str = ""
    url: str = ""
    message: str = ""


class FormJob(BaseModel):
    job_id: str
    url: str
    profile: JobProfile
    options: JobOptions = Field(default_factory=JobOptions)
    created_at: datetime = Field(default_factory=datetime.now)


class JobStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    CAPTCHA_BLOCKED = "captcha_blocked"
    FORM_NOT_FOUND = "form_not_found"
    SKIPPED = "skipped"


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    url: str
    fields_filled: int = 0
    fields_total: int = 0
    fields_skipped: list[str] = Field(default_factory=list)
    screenshot_before: str | None = None
    screenshot_after: str | None = None
    error: str | None = None
    completed_at: datetime = Field(default_factory=datetime.now)
