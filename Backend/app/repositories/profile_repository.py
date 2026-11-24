from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.student_profile import StudentProfile


class ProfileRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, profile_data: dict) -> StudentProfile:
        profile = StudentProfile(**profile_data)
        self.db.add(profile)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def get_by_id(self, profile_id: str) -> StudentProfile | None:
        return self.db.query(StudentProfile).filter(StudentProfile.id == profile_id).first()

    def update(self, profile: StudentProfile, updates: dict) -> StudentProfile:
        for key, value in updates.items():
            if value is not None:
                setattr(profile, key, value)
        self.db.commit()
        self.db.refresh(profile)
        return profile
