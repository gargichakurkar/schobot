from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StudentProfileBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=255)
    email: str | None = None
    education_level: str | None = None
    course: str | None = None
    study_year: str | None = None
    college_name: str | None = None
    academic_score: float | None = None
    score_type: str | None = None
    domicile_state: str | None = None
    study_state: str | None = None
    category: str | None = None
    gender: str | None = None
    # Disability-related information
    disability_percentage: float | None = None
    has_valid_disability_certificate: bool | None = None
    has_udid: bool | None = None

    # Swanath-related information
    is_orphan: bool | None = None
    parent_death_due_to_covid: bool | None = None
    parent_martyred_armed_forces: bool | None = None

    # Railway scholarship information
    is_dependent_of_rpf_rpsf: bool | None = None
    parent_service_category: str | None = None

    # Academic and other scholarship conditions
    previous_year_passed: bool | None = None
    receives_other_scholarship: bool | None = None
    # Disability-related information
    disability_percentage: float | None = None
    has_valid_disability_certificate: bool | None = None
    has_udid: bool | None = None

    # Swanath-related information
    is_orphan: bool | None = None
    parent_death_due_to_covid: bool | None = None
    parent_martyred_armed_forces: bool | None = None

    # Railway scholarship information
    is_dependent_of_rpf_rpsf: bool | None = None
    parent_service_category: str | None = None

    # Academic and other scholarship conditions
    previous_year_passed: bool | None = None
    receives_other_scholarship: bool | None = None
    has_disability_certificate: bool | None = None
    annual_family_income: float | None = None
    has_income_certificate: bool | None = None
    profile_completed: bool = False


class StudentProfileCreate(StudentProfileBase):
    pass


class StudentProfileUpdate(BaseModel):
    full_name: str | None = None
    email: str | None = None
    education_level: str | None = None
    course: str | None = None
    study_year: str | None = None
    college_name: str | None = None
    academic_score: float | None = None
    score_type: str | None = None
    domicile_state: str | None = None
    study_state: str | None = None
    category: str | None = None
    gender: str | None = None
    has_disability_certificate: bool | None = None
    annual_family_income: float | None = None
    has_income_certificate: bool | None = None
    profile_completed: bool | None = None


class StudentProfileResponse(StudentProfileBase):
    id: str
    model_config = ConfigDict(from_attributes=True)
