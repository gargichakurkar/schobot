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
            .filter(func.lower(StudentProfile.email) == PROFILE_EMAIL.lower())
            .order_by(StudentProfile.created_at.desc())
            .first()
        )
        if profile is None:
            print(f"No student profile found for {PROFILE_EMAIL!r}.")
            print("Replace PROFILE_EMAIL at the top of Backend/test_recs.py with the email used to save the profile.")
            return 1

        matches = (
            session.query(ScholarshipMatch, Scholarship)
            .join(Scholarship, Scholarship.id == ScholarshipMatch.scholarship_id)
            .filter(ScholarshipMatch.student_id == profile.id)
            .all()
        )
        recommendations = [
            {
                "name": scholarship.scholarship_name,
                "match_tags": [
                    rule.get("label", rule.get("field", ""))
                    for rule in (match.passed_rules or [])
                    if rule.get("field") in {"domicile_state", "category", "education_level", "course", "income"}
                ],
                "match_status": match.match_status,
            }
            for match, scholarship in matches
        ]

        print(f"Profile ID: {profile.id}")
        print(f"Education level: {profile.education_level or 'Unknown'}")
        print(f"Category: {profile.category or 'Unknown'}")
        print(f"Domicile state: {profile.domicile_state or 'Unknown'}")
        print(f"Annual family income: {profile.annual_family_income if profile.annual_family_income is not None else 'Unknown'}")
        print(f"Number of recommendations: {len(recommendations)}")
        print("First 10 recommendations:")
        for recommendation in recommendations[:10]:
            print(
                f"- {recommendation['name']} "
                f"[{recommendation['match_status']}] "
                f"match_tags={recommendation['match_tags']}"
            )
        if not recommendations:
            print("No saved recommendations found. Save the profile again to compute and store current matches.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
