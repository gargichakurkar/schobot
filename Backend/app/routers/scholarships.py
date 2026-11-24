from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.schemas.recommendation import ScholarshipEligibilityResponse
from app.schemas.scholarship import ScholarshipResponse
from app.services.rule_engine import evaluate_eligibility
from app.utils.dedupe import dedupe_by_scholarship_id

router = APIRouter(prefix="/api", tags=["scholarships"])


@router.get("/scholarships", response_model=list[ScholarshipResponse])
def list_scholarships(
    search: str | None = Query(default=None, min_length=1, max_length=200),
    state: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=255),
    education: str | None = Query(default=None, max_length=200),
    scholarship_type: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
) -> list[Scholarship]:
    query = db.query(Scholarship).filter(Scholarship.scholarship_name != "Untitled Scholarship")
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Scholarship.scholarship_name.ilike(term),
                Scholarship.provider.ilike(term),
                Scholarship.description.ilike(term),
                Scholarship.benefits.ilike(term),
            )
        )
    if state and state.strip():
        selected_state = state.strip()
        state_filter = Scholarship.state.ilike(selected_state)
        if selected_state.casefold() != "all india":
            state_filter = or_(state_filter, Scholarship.state.ilike("All India"))
        query = query.filter(state_filter)
    if category and category.strip():
        query = query.filter(Scholarship.category.ilike(f"%{category.strip()}%"))
    if education and education.strip():
        term = f"%{education.strip()}%"
        query = query.filter(
            or_(
                Scholarship.eligible_level.ilike(term),
                Scholarship.qualification_text.ilike(term),
            )
        )
    if scholarship_type and scholarship_type.strip():
        query = query.filter(Scholarship.scholarship_type.ilike(scholarship_type.strip()))
    records = query.order_by(Scholarship.scholarship_name, Scholarship.state).all()
    return dedupe_by_scholarship_id(
        [ScholarshipResponse.model_validate(record).model_dump() for record in records]
    )


@router.get("/scholarships/{scholarship_id}", response_model=ScholarshipResponse)
def get_scholarship(scholarship_id: str, db: Session = Depends(get_db)) -> ScholarshipResponse:
    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return scholarship


@router.get("/scholarships/{scholarship_id}/eligibility/{student_id}")
def get_eligibility_for_scholarship(scholarship_id: str, student_id: str, db: Session = Depends(get_db)):
    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    result = evaluate_eligibility(student, scholarship)
    return {
        "student": student,
        "scholarship": scholarship,
        "match_status": result["match_status"],
        "match_score": result["match_score"],
        "passed_rules": result["passed_rules"],
        "failed_rules": result["failed_rules"],
        "unknown_rules": result["unknown_rules"],
        "warnings": result["warnings"],
    }
