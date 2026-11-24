from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.repositories.scholarship_repository import ScholarshipRepository


class ScholarshipService:
    def __init__(self, db: Session):
        self.repo = ScholarshipRepository(db)

    def list_scholarships(self):
        return self.repo.list_all()

    def list_active_scholarships(self):
        return self.repo.list_active()

    def get_scholarship(self, scholarship_id: str) -> Scholarship | None:
        return self.repo.get_by_id(scholarship_id)
