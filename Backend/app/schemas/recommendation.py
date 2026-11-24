from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.scholarship import ScholarshipResponse
from app.schemas.student_profile import StudentProfileResponse


class RuleResult(BaseModel):
    field: str
    label: str
    student_value: Any | None = None
    requirement: Any | None = None
    status: str
    message: str


class RecommendationMatch(BaseModel):
    scholarship_id: str
    scholarship_name: str
    state: str | None = None
    scholarship_type: str | None = None
    deadline: datetime | None = None
    official_link: str | None = None
    match_status: str
    match_score: float
    doc_status: str = "not_started"
    notes: str | None = None
    passed_rules: list[RuleResult] = []
    failed_rules: list[RuleResult] = []
    unknown_rules: list[RuleResult] = []
    warnings: list[RuleResult] = []


class RecommendationResponse(BaseModel):
    student: StudentProfileResponse
    recommendations: list[RecommendationMatch]
    best_bets: list[dict[str, Any]] = []
    model_config = ConfigDict(from_attributes=True)


class EligibilityDetail(BaseModel):
    match_status: str
    match_score: float
    passed_rules: list[RuleResult] = []
    failed_rules: list[RuleResult] = []
    unknown_rules: list[RuleResult] = []
    warnings: list[RuleResult] = []
    scholarship: ScholarshipResponse | None = None


class ScholarshipEligibilityResponse(BaseModel):
    student: StudentProfileResponse
    scholarship: ScholarshipResponse
    eligibility: EligibilityDetail
