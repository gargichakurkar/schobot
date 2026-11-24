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
    return profile


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
