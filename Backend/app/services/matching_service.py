from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.repositories.match_repository import MatchRepository
from app.services.rule_engine import evaluate_eligibility
from app.services.ranking_service import sort_matches


class MatchingService:
    def __init__(self, db: Session):
        self.db = db
        self.match_repo = MatchRepository(db)

    def evaluate_student_for_all_scholarships(self, student: StudentProfile):
        scholarships = self.db.query(Scholarship).filter(Scholarship.is_active.is_(True)).all()
        matches = []
        for scholarship in scholarships:
            result = evaluate_eligibility(student, scholarship)
            match_data = {
                "student_id": student.id,
                "scholarship_id": scholarship.id,
                "match_status": result["match_status"],
                "match_score": result["match_score"],
                "passed_rules": result["passed_rules"],
                "failed_rules": result["failed_rules"],
                "unknown_rules": result["unknown_rules"],
                "warnings": result["warnings"],
            }
            saved_match = self.match_repo.create(match_data)
            matches.append(
                {
                    "id": saved_match.id,
                    "student_id": saved_match.student_id,
                    "scholarship_id": saved_match.scholarship_id,
                    "match_status": saved_match.match_status,
                    "match_score": saved_match.match_score,
                    "passed_rules": saved_match.passed_rules,
                    "failed_rules": saved_match.failed_rules,
                    "unknown_rules": saved_match.unknown_rules,
                    "warnings": saved_match.warnings,
                    "scholarship": scholarship,
                }
            )
        return sort_matches(matches)
