from __future__ import annotations

from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.schemas.new_features import EligibilitySimulationRequest
from app.services.best_bets_service import compute_best_bets
from app.services.rule_engine import evaluate_eligibility

router = APIRouter(prefix="/api/simulate", tags=["simulation"])
ELIGIBLE_STATUSES = {"likely_eligible", "needs_verification"}


@router.post("/eligibility")
def simulate_eligibility(payload: EligibilitySimulationRequest, db: Session = Depends(get_db)) -> dict:
    base = db.query(StudentProfile).filter(StudentProfile.id == payload.base_student_id).first()
    if base is None:
        raise HTTPException(status_code=404, detail="Student profile not found")

    fields = (
        "id", "full_name", "email", "education_level", "course", "study_year", "college_name",
        "academic_score", "score_type", "domicile_state", "study_state", "category", "gender",
        "has_disability_certificate", "annual_family_income", "has_income_certificate", "profile_completed",
    )
    simulated_values = {field: getattr(base, field) for field in fields}
    simulated_values.update(payload.overrides.model_dump(exclude_unset=True))
    simulated = SimpleNamespace(**simulated_values)
    scholarships = db.query(Scholarship).filter(Scholarship.is_active.is_(True)).all()

    def eligible_ids(profile) -> set[str]:
        return {
            scholarship.id for scholarship in scholarships
            if evaluate_eligibility(profile, scholarship)["match_status"] in ELIGIBLE_STATUSES
        }

    base_ids = eligible_ids(base)
    simulated_ids = eligible_ids(simulated)
    names = {scholarship.id: scholarship.scholarship_name for scholarship in scholarships}
    return {
        "eligible_count": len(simulated_ids),
        "best_bets": compute_best_bets(simulated, db),
        "changed_vs_base": {
            "newly_eligible": [
                {"scholarship_id": item, "scholarship_name": names[item]}
                for item in sorted(simulated_ids - base_ids, key=lambda value: names[value].casefold())
            ],
            "no_longer_eligible": [
                {"scholarship_id": item, "scholarship_name": names[item]}
                for item in sorted(base_ids - simulated_ids, key=lambda value: names[value].casefold())
            ],
        },
    }
