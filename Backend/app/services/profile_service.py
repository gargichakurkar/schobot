from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.student_profile import StudentProfile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.student_profile import StudentProfileCreate, StudentProfileUpdate


class ProfileService:
    def __init__(self, db: Session):
        self.repo = ProfileRepository(db)

    def create_profile(self, payload: StudentProfileCreate) -> StudentProfile:
        data = payload.model_dump(exclude_none=True)
        return self.repo.create(data)

    def get_profile(self, profile_id: str) -> StudentProfile | None:
        return self.repo.get_by_id(profile_id)

    def update_profile(self, profile_id: str, payload: StudentProfileUpdate) -> StudentProfile:
        profile = self.repo.get_by_id(profile_id)
        if profile is None:
            raise ValueError("Student profile not found")
        updates = payload.model_dump(exclude_none=True)
        return self.repo.update(profile, updates)
