from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.models.scholarship_match import ScholarshipMatch
from app.models.student_profile import StudentProfile
from app.services.rule_engine import evaluate_eligibility
from app.services.ranking_service import sort_matches


class MatchingService:
    def __init__(self, db: Session):
        self.db = db

    def recalculate_matches_for_student(self, student: StudentProfile) -> list[ScholarshipMatch]:
        scholarships = (
            self.db.query(Scholarship)
            .filter(
                Scholarship.scholarship_name != "Untitled Scholarship",
                or_(
                    Scholarship.is_active.is_(True),
                    Scholarship.active_status == "unknown",
                ),
            )
            .all()
        )
        existing_matches = {
            m.scholarship_id: m
            for m in self.db.query(ScholarshipMatch).filter(ScholarshipMatch.student_id == student.id).all()
        }
        active_ids = {s.id for s in scholarships}

        for sch_id, m in list(existing_matches.items()):
            if sch_id not in active_ids:
                self.db.delete(m)

        result_matches: list[ScholarshipMatch] = []
        now = datetime.now(timezone.utc)
        for scholarship in scholarships:
            result = evaluate_eligibility(student, scholarship)
            if scholarship.id in existing_matches:
                match = existing_matches[scholarship.id]
                match.match_status = result["match_status"]
                match.match_score = result["match_score"]
                match.passed_rules = result["passed_rules"]
                match.failed_rules = result["failed_rules"]
                match.unknown_rules = result["unknown_rules"]
                match.warnings = result["warnings"]
                match.updated_at = now
            else:
                match = ScholarshipMatch(
                    student_id=student.id,
                    scholarship_id=scholarship.id,
                    match_status=result["match_status"],
                    match_score=result["match_score"],
                    passed_rules=result["passed_rules"],
                    failed_rules=result["failed_rules"],
                    unknown_rules=result["unknown_rules"],
                    warnings=result["warnings"],
                    calculated_at=now,
                    updated_at=now,
                )
                self.db.add(match)
            result_matches.append(match)

        self.db.commit()
        return result_matches

    def evaluate_student_for_all_scholarships(self, student: StudentProfile):
        matches = self.recalculate_matches_for_student(student)
        scholarships_by_id = {
            s.id: s
            for s in self.db.query(Scholarship).filter(Scholarship.id.in_([m.scholarship_id for m in matches])).all()
        }
        formatted = []
        for match in matches:
            formatted.append(
                {
                    "id": match.id,
                    "student_id": match.student_id,
                    "scholarship_id": match.scholarship_id,
                    "match_status": match.match_status,
                    "match_score": match.match_score,
                    "passed_rules": match.passed_rules,
                    "failed_rules": match.failed_rules,
                    "unknown_rules": match.unknown_rules,
                    "warnings": match.warnings,
                    "scholarship": scholarships_by_id.get(match.scholarship_id),
                }
            )
        return sort_matches(formatted)
