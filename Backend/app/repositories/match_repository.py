from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.scholarship_match import ScholarshipMatch


class MatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, match_data: dict) -> ScholarshipMatch:
        match = ScholarshipMatch(**match_data)
        self.db.add(match)
        self.db.commit()
        self.db.refresh(match)
        return match

    def list_for_student(self, student_id: str):
        return self.db.query(ScholarshipMatch).filter(ScholarshipMatch.student_id == student_id).all()
