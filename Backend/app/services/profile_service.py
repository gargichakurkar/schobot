from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.student_profile import StudentProfile
from app.repositories.profile_repository import ProfileRepository
from app.schemas.student_profile import StudentProfileCreate, StudentProfileUpdate


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = ProfileRepository(db)

    def create_profile(self, payload: StudentProfileCreate) -> StudentProfile:
        email = (payload.email or "").strip()
        if email:
            existing = self.repo.get_by_email(email)
            if existing:
                raise ValueError("An account with this email address already exists. Please sign in or reset your password.")

        data = payload.model_dump(exclude_none=True)
        password = data.pop("password", None)
        if password:
            from auth import hash_password
            data["password_hash"] = hash_password(password)
        return self.repo.create(data)

    def get_profile(self, profile_id: str) -> StudentProfile | None:
        return self.repo.get_by_id(profile_id)

    def update_profile(self, profile_id: str, payload: StudentProfileUpdate) -> StudentProfile:
        profile = self.repo.get_by_id(profile_id)
        if profile is None:
            raise ValueError("Student profile not found")
        updates = payload.model_dump(exclude_none=True)
        updated_profile = self.repo.update(profile, updates)

        from app.services.matching_service import MatchingService
        MatchingService(self.db).recalculate_matches_for_student(updated_profile)
        return updated_profile
