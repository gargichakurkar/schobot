from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.counselor_link import CounselorLink
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.schemas.new_features import CounselorLinkRequest
from app.services.best_bets_service import compute_best_bets
from app.services.rule_engine import evaluate_eligibility
from app.utils.eligibility_helpers import parse_date
from auth import get_current_student

router = APIRouter(prefix="/api/counselor", tags=["counselor"])
ELIGIBLE_STATUSES = {"likely_eligible", "needs_verification"}


@router.post("/link")
def create_counselor_link(
    payload: CounselorLinkRequest,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> dict:
    if payload.student_id and payload.student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot create or replace counselor links for another student.",
        )
    student_id = current_student.id
    link = db.query(CounselorLink).filter(CounselorLink.student_id == student_id).first()
    expiry = datetime.now(timezone.utc) + timedelta(days=30)
    if link is None:
        link = CounselorLink(
            student_id=student_id,
            counselor_email=str(payload.counselor_email),
            language=payload.language,
            token=secrets.token_urlsafe(32),
            expires_at=expiry,
            is_revoked=False,
        )
        db.add(link)
    else:
        link.counselor_email = str(payload.counselor_email)
        link.language = payload.language
        link.token = secrets.token_urlsafe(32)
        link.expires_at = expiry
        link.is_revoked = False
    db.commit()
    db.refresh(link)
    return {
        "language": link.language,
        "token": link.token,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "delivery_status": "not_configured",
    }


@router.delete("/link")
def revoke_counselor_link(
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> dict:
    link = db.query(CounselorLink).filter(CounselorLink.student_id == current_student.id).first()
    if link is None:
        raise HTTPException(status_code=404, detail="No active counselor link found.")
    link.is_revoked = True
    db.commit()
    return {"status": "success", "message": "Counselor link revoked successfully."}


@router.get("/view/{token}")
def get_counselor_view(token: str, db: Session = Depends(get_db)) -> dict:
    link = db.query(CounselorLink).filter(CounselorLink.token == token).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Counselor link not found")
    if getattr(link, "is_revoked", False):
        raise HTTPException(status_code=403, detail="Counselor access link has been revoked by the student.")
    exp = getattr(link, "expires_at", None)
    if exp:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Counselor access link has expired.")
    student = db.query(StudentProfile).filter(StudentProfile.id == link.student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    scholarships = db.query(Scholarship).filter(Scholarship.is_active.is_(True)).all()
    evaluations = {
        scholarship.id: evaluate_eligibility(student, scholarship) for scholarship in scholarships
    }
    eligible = [
        {
            "scholarship_id": scholarship.id,
            "scholarship_name": scholarship.scholarship_name,
            "deadline": scholarship.deadline,
        }
        for scholarship in scholarships
        if evaluations[scholarship.id]["match_status"] in ELIGIBLE_STATUSES
    ]
    cutoff = date.today() + timedelta(days=60)
    upcoming: list[dict] = []
    for scholarship in scholarships:
        deadline = parse_date(scholarship.deadline)
        if deadline and date.today() <= deadline <= cutoff:
            upcoming.append({"scholarship_name": scholarship.scholarship_name, "label": "Application deadline", "date": deadline})
        for milestone in scholarship.milestones or []:
            if not isinstance(milestone, dict):
                continue
            milestone_date = parse_date(milestone.get("date"))
            if milestone_date and date.today() <= milestone_date <= cutoff:
                upcoming.append({
                    "scholarship_name": scholarship.scholarship_name,
                    "label": str(milestone.get("label") or milestone.get("milestone_type") or "Milestone"),
                    "date": milestone_date,
                })
    upcoming.sort(key=lambda item: (item["date"], item["scholarship_name"].casefold()))
    return {
        "language": link.language,
        "student": {
            "full_name": student.full_name,
            "education_level": student.education_level,
            "course": student.course,
            "category": student.category,
            "domicile_state": student.domicile_state,
            "annual_family_income": student.annual_family_income,
        },
        "eligible_count": len(eligible),
        "recommendations": eligible,
        "best_bets": compute_best_bets(student, db),
        "upcoming_deadlines": upcoming,
    }
