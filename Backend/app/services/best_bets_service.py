from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.scholarship import Scholarship
from app.services.rule_engine import _category_matches, _course_matches, _normalize_level, evaluate_eligibility


def _value(profile: Any, name: str) -> Any:
    return profile.get(name) if isinstance(profile, dict) else getattr(profile, name, None)


def compute_best_bets(profile: Any, session: Session, top_n: int = 5) -> list[dict]:
    """Rank active eligible scholarships using profile fit signals."""
    scholarships = session.query(Scholarship).filter(Scholarship.is_active.is_(True)).all()
    ranked: list[dict] = []
    category = _value(profile, "category")
    domicile = str(_value(profile, "domicile_state") or _value(profile, "study_state") or "").strip().lower()
    income = _value(profile, "annual_family_income")
    try:
        income = float(income) if income is not None else None
    except (TypeError, ValueError):
        income = None

    for scholarship in scholarships:
        evaluation = evaluate_eligibility(profile, scholarship)
        if evaluation["match_status"] not in {"likely_eligible", "needs_verification"}:
            continue

        score = 0.0
        weight = 0.0
        reason_tags: list[str] = []
        scholarship_category = scholarship.category
        if category and scholarship_category:
            weight += 0.3
            if _category_matches(category, scholarship_category):
                category_label = str(category).strip()
                category_weight = 0.4 if category_label.lower() in {"obc", "sc", "st", "sc/st", "vjnt", "pwd"} else 0.3
                score += category_weight
                weight += category_weight - 0.3
                reason_tags.append(category_label)

        state = str(scholarship.state or "").strip().lower()
        if state and domicile:
            weight += 0.25
            if state in {"all india", "pan india", "all states", "india"} or state == domicile:
                score += 0.25
                if domicile in {"maharashtra", "mh"} and state in {"maharashtra", "mh"}:
                    reason_tags.append("Maharashtra domicile")

        if scholarship.max_income is not None and income is not None and scholarship.max_income > 0:
            weight += 0.2
            if income <= scholarship.max_income:
                score += 0.1 + 0.1 * (income / scholarship.max_income)
                reason_tags.append("Income fit")

        student_level = _normalize_level(_value(profile, "education_level"))
        required_level = _normalize_level(scholarship.eligible_level)
        if student_level and required_level:
            weight += 0.15
            if student_level == required_level:
                score += 0.15
                reason_tags.append("Education fit")

        student_course = _value(profile, "course")
        if student_course and scholarship.eligible_course:
            weight += 0.1
            if _course_matches(student_course, scholarship.eligible_course):
                score += 0.1
                reason_tags.append("Course fit")

        normalized_score = round(score / weight, 2) if weight else round(evaluation["match_score"] / 100, 2)
        ranked.append({
            "scholarship_id": scholarship.id,
            "scholarship_name": scholarship.scholarship_name,
            "score": normalized_score,
            "reason_tags": reason_tags,
        })

    ranked.sort(key=lambda item: (-item["score"], item["scholarship_name"].casefold()))
    return ranked[:max(0, top_n)]
