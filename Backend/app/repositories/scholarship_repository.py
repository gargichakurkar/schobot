from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship


class ScholarshipRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_all(self):
        return self.db.query(Scholarship).order_by(Scholarship.scholarship_name).all()

    def list_active(self):
        return self.db.query(Scholarship).filter(Scholarship.is_active.is_(True)).order_by(Scholarship.scholarship_name).all()

    def get_by_id(self, scholarship_id: str) -> Scholarship | None:
        return self.db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()

    def create_or_update(self, scholarship_data: dict) -> Scholarship:
        scholarship_id = scholarship_data.get("id")
        scholarship = self.db.query(Scholarship).filter(Scholarship.id == scholarship_id).first() if scholarship_id else None
        if scholarship is None:
            scholarship = Scholarship(**scholarship_data)
            self.db.add(scholarship)
        else:
            for key, value in scholarship_data.items():
                if value is not None:
                    setattr(scholarship, key, value)
        self.db.commit()
        self.db.refresh(scholarship)
        return scholarship
