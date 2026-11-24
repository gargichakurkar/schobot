from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ScholarshipBase(BaseModel):
    dataset_id: str | None = None
    scholarship_name: str = Field(..., min_length=1, max_length=255)
    provider: str | None = None
    state: str | None = None
    category: str | None = None
    additional_category_requirements: str | None = None
    income_text: str | None = None
    additional_income_requirements: str | None = None
    qualification_text: str | None = None
    description: str | None = None
    benefits: str | None = None
    required_documents: str | None = None
    eligibility_details: str | None = None
    official_link: str | None = None
    scheme_info_link: str | None = None
    scholarship_type: str | None = None
    max_income: float | None = None
    min_percentage: float | None = None
    minimum_marks_text: str | None = None
    additional_education_requirements: str | None = None
    eligible_level: str | None = None
    eligible_course: str | None = None
    gender_requirement: str | None = None
    year_text: str | None = None
    source_filename: str | None = None
    source_identifier: str | None = None
    active_status: str | None = None
    deadline: datetime | None = None
    milestones: list[dict[str, Any]] | None = None
    is_active: bool = True


class ScholarshipCreate(ScholarshipBase):
    pass


class ScholarshipResponse(ScholarshipBase):
    id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)
