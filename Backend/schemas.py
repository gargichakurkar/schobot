from pydantic import BaseModel, Field
from typing import Optional


# ============================================================
# STUDENT PROFILE
# ============================================================

class StudentProfileCreate(BaseModel):

    name: str = Field(
        ...,
        min_length=1,
        max_length=200
    )

    age: Optional[int] = None

    gender: Optional[str] = None

    state: Optional[str] = None

    category: Optional[str] = None

    family_income: Optional[float] = None

    qualification: Optional[str] = None

    education_stage: Optional[str] = None

    course: Optional[str] = None

    stream: Optional[str] = None

    percentage: Optional[float] = None

    disability: Optional[str] = None

    minority: Optional[str] = None

    sports: Optional[str] = None

    exserviceman: Optional[str] = None


class StudentProfileResponse(StudentProfileCreate):

    id: int

    class Config:
        from_attributes = True


# ============================================================
# SCHOLARSHIP RESPONSE
# ============================================================

class ScholarshipResponse(BaseModel):

    id: int

    scheme_name: str

    eligibility: Optional[str] = None

    details: Optional[str] = None

    tags: Optional[str] = None

    application_process: Optional[str] = None

    benefits: Optional[str] = None

    documents_required: Optional[str] = None

    source_url: Optional[str] = None

    department: Optional[str] = None

    target_states: Optional[str] = None

    verification_status: Optional[str] = None

    class Config:
        from_attributes = True