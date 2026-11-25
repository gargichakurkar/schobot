from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.student_profile import StudentProfileCreate, StudentProfileResponse, StudentProfileUpdate
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/api", tags=["profiles"])


@router.post("/profiles", response_model=StudentProfileResponse)
def create_profile(payload: StudentProfileCreate, db: Session = Depends(get_db)) -> StudentProfileResponse:
    service = ProfileService(db)
    profile = service.create_profile(payload)
    resp = StudentProfileResponse.model_validate(profile)
    try:
        from auth import create_access_token
        resp.access_token = create_access_token({"sub": profile.id, "role": "student"})
    except Exception:
        pass
    return resp


@router.post("/auth/token")
def issue_student_token(payload: dict, db: Session = Depends(get_db)) -> dict:
    from app.models.student_profile import StudentProfile
    student_id = payload.get("student_id")
    if not student_id:
        raise HTTPException(status_code=422, detail="student_id is required")
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    from auth import create_access_token
    token = create_access_token({"sub": student.id, "role": "student"})
    return {"access_token": token, "token_type": "bearer", "student_id": student.id}


@router.get("/profiles/{student_id}", response_model=StudentProfileResponse)
def get_profile(student_id: str, db: Session = Depends(get_db)) -> StudentProfileResponse:
    service = ProfileService(db)
    profile = service.get_profile(student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


@router.put("/profiles/{student_id}", response_model=StudentProfileResponse)
def update_profile(student_id: str, payload: StudentProfileUpdate, db: Session = Depends(get_db)) -> StudentProfileResponse:
    service = ProfileService(db)
    try:
        profile = service.update_profile(student_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile
