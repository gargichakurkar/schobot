from __future__ import annotations

import sys

from sqlalchemy import func

from app.core.database import SessionLocal
from app.models.scholarship import Scholarship
from app.models.scholarship_match import ScholarshipMatch
from app.models.student_profile import StudentProfile

PROFILE_EMAIL = "replace-with-your-email@example.com"


def main() -> int:
    session = SessionLocal()
    try:
        profile = (
            session.query(StudentProfile)
            .filter(func.lower(StudentProfile.email) == PROFILE_EMAIL.strip().lower())
            .order_by(StudentProfile.created_at.desc())
            .first()
        )
        if profile is None:
            print(f"No student profile found for {PROFILE_EMAIL!r}.")
            print("Set PROFILE_EMAIL at the top of Backend/check_eligible.py to the email used to save the profile.")
            return 1

        matches = (
            session.query(ScholarshipMatch)
            .filter(ScholarshipMatch.student_id == profile.id)
            .all()
        )
        print(f"Profile ID: {profile.id}")
        print(f"Profile email: {profile.email}")
        print(f"Total scholarship match rows: {len(matches)}")

        for match in matches:
            scholarship = session.get(Scholarship, match.scholarship_id)
            scholarship_name = scholarship.scholarship_name if scholarship else "[scholarship record missing]"
            score = match.match_score if match.match_score is not None else "not available"
            print(f"- {scholarship_name} | status={match.match_status} | score={score}")

        if not matches:
            print("No saved scholarship matches found. Save the profile again to calculate eligibility.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
