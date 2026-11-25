from __future__ import annotations

from typing import Literal

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EligibilityOverrides(BaseModel):
    annual_family_income: float | None = Field(default=None, ge=0)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    education_level: str | None = Field(default=None, min_length=1, max_length=100)
    course: str | None = Field(default=None, min_length=1, max_length=150)

    model_config = ConfigDict(extra="forbid")


class EligibilitySimulationRequest(BaseModel):
    base_student_id: str = Field(min_length=1, max_length=36)
    overrides: EligibilityOverrides

    model_config = ConfigDict(extra="forbid")


class ReminderPreferenceRequest(BaseModel):
    student_id: str = Field(min_length=1, max_length=36)
    scholarship_id: str = Field(min_length=1, max_length=36)
    channel: Literal["email", "sms", "whatsapp"]
    enabled: bool


class CounselorLinkRequest(BaseModel):
    student_id: str | None = Field(default=None, min_length=1, max_length=36)
    counselor_email: str = Field(min_length=3, max_length=255)
    language: Literal["en", "mr"] = "en"

    @field_validator("counselor_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("Enter a valid counselor email address")
        return normalized
