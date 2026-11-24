from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime
from typing import Any

from app.utils.eligibility_helpers import parse_date

logger = logging.getLogger(__name__)
_debug_evaluation_logged = False


def _get_value(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _rule(field: str, label: str, student_value: Any, requirement: Any, status: str, message: str) -> dict:
    return {
        "field": field,
        "label": label,
        "student_value": student_value,
        "requirement": requirement,
        "status": status,
        "message": message,
    }


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()

def _normalize_category(value: Any) -> str:
    category = re.sub(r"[^a-z0-9]+", " ", _normalize(value)).strip()
    aliases = {
        "sebc": "obc",
        "sc": "sc st",
        "st": "sc st",
        "sc st": "sc st",
        "pwd": "pwd",
        "vjnt": "vjnt",
    }
    return aliases.get(category, category)


def _category_matches(student_category: Any, scholarship_category: Any) -> bool:
    scholarship_value = _normalize(scholarship_category)
    if not scholarship_value:
        return False
    normalized_scholarship = re.sub(r"[^a-z0-9]+", " ", scholarship_value).strip()
    if normalized_scholarship in {"all", "all categories", "all students", "any category"}:
        return True

    accepted_categories = re.split(r"\s*(?:/|,|;|\bor\b|\band\b)\s*", scholarship_value)
    student_value = _normalize_category(student_category)
    return bool(student_value) and student_value in {
        _normalize_category(category) for category in accepted_categories
    }


def _course_matches(student_course: Any, scholarship_course: Any) -> bool:
    s = _normalize(student_course)
    sc = _normalize(scholarship_course)
    if not s or not sc:
        return False
    if re.sub(r"[^a-z0-9]+", " ", sc).strip() in {
        "all", "all courses", "all students", "any course", "any discipline",
    }:
        return True
    if s == sc:
        return True
    if s in sc or sc in s:
        return True
    if "b.tech" in s and "b.tech" in sc:
        return True
    if "bsc" in s and "bsc" in sc:
        return True
    return False

def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = re.sub(r"[₹,\s]", "", value)
        if not value:
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_level(value: Any) -> str:
    value = _normalize(value)
    if not value:
        return ""
    mapping = {
        "undergraduate": "undergraduate",
        "graduation": "undergraduate",
        "b.tech": "undergraduate",
        "bsc": "undergraduate",
        "class 9": "class 9",
        "class 10": "class 10",
        "10th": "class 10",
        "class 11": "class 11-12",
        "class 11-12": "class 11-12",
        "class 12": "class 11-12",
        "11th": "class 11-12",
        "12th": "class 11-12",
        "diploma": "diploma",
        "postgraduate": "postgraduate",
        "masters": "postgraduate",
        "master": "postgraduate",
        "mba": "postgraduate",
        "phd": "phd",
        "doctorate": "phd",
    }
    for key, mapped in mapping.items():
        if key in value:
            return mapped
    return value


def _education_levels(value: Any) -> set[str]:
    text = _normalize(value).replace("?", "-").replace("?", "-")
    levels: set[str] = set()

    if re.search(r"(?:1st|class\s*1)\s*(?:to|-)\s*(?:10th|class\s*10)", text):
        levels.update({"class 9", "class 10"})

    if re.search(
        r"(?:class(?:es)?\s*)?11\s*(?:and|&|or|-)\s*(?:class(?:es)?\s*)?12|11th\s*(?:and|&|or)\s*12th",
        text,
    ):
        levels.add("class 11-12")
    elif re.search(r"\b(?:class\s*11|11th|fyjc|syjc)\b", text):
        levels.add("class 11-12")
    elif re.search(r"\b(?:class\s*12|12th|hsc)\b", text):
        levels.add("class 11-12")

    is_postgraduate = bool(
        re.search(r"\b(?:postgraduate|post[\s-]?graduation|postgrad|master|ph\.?d|doctorate)\b", text)
    )

    if is_postgraduate:
        levels.add("postgraduate")

    # Explicit post-matric range from Class 11 through PhD
    # includes school, undergraduate and postgraduate education.
    if re.search(
        r"\b(?:class\s*)?11\s+to\s+(?:ph\.?d|doctorate)\b",
        text,
    ):
        levels.update({"class 11-12", "undergraduate", "postgraduate"})

    if re.search(
        r"\b(?:undergraduate|under[\s-]?graduation|undergrad|bachelor|b\.?tech|b\.?sc|b\.?e\.?)\b",
        text,
    ):
        levels.add("undergraduate")
    elif "degree" in text and not is_postgraduate:
        levels.add("undergraduate")

    if re.search(r"\b(?:diploma|polytechnic)\b", text):
        levels.add("diploma")

    return levels


def _education_years(value: Any) -> set[int]:
    text = _normalize(value).replace("-", " ")
    words = {
        "first": 1, "1st": 1,
        "second": 2, "2nd": 2,
        "third": 3, "3rd": 3,
        "fourth": 4, "4th": 4,
    }
    years = set()

    for word, number in words.items():
        if re.search(rf"\b{word}\s+year\b", text):
            years.add(number)

    for match in re.finditer(r"\byear\s*([1-4])\b", text):
        years.add(int(match.group(1)))

    return years

def _is_unmodeled_category(value: Any) -> bool:
    category = _normalize(value)
    return any(
        marker in category
        for marker in (
            "ward of",
            "wards of",
            "worker",
            "muslim",
            "christian",
            "sikh",
            "buddhist",
            "buddha",
            "jain",
            "parsi",
            "jews",
        )
    )


def _log_debug_evaluation(student: Any, scholarship: Any, result: dict) -> None:
    global _debug_evaluation_logged
    if os.getenv("SCHOBOT_DEBUG_ELIGIBILITY") != "1" or _debug_evaluation_logged:
        return

    student_fields = {
        field: _get_value(student, field)
        for field in ("domicile_state", "category", "annual_family_income", "education_level", "course")
    }
    scholarship_fields = {
        field: _get_value(scholarship, field)
        for field in ("state", "category", "max_income", "eligible_level", "eligible_course")
    }
    outcomes = [
        (rule["field"], rule["status"])
        for rule in (*result["passed_rules"], *result["failed_rules"], *result["unknown_rules"])
    ]
    logger.info(
        "Eligibility diagnostic student=%s scholarship=%s outcomes=%s match_status=%s",
        student_fields,
        scholarship_fields,
        outcomes,
        result["match_status"],
    )
    _debug_evaluation_logged = True


def evaluate_eligibility(student: Any, scholarship: Any) -> dict:
    """Evaluate scholarship eligibility using transparent deterministic rules.

    The function intentionally returns structured rule objects rather than opaque booleans,
    which makes the recommendation explainable and auditable.
    """

    # student and scholarship may be ORM models or plain dictionaries
    student_value = lambda name, default=None: _get_value(student, name, default)
    scholarship_value = lambda name, default=None: _get_value(scholarship, name, default)

    passed_rules: list[dict] = []
    failed_rules: list[dict] = []
    unknown_rules: list[dict] = []
    warnings: list[dict] = []

    # 1. Active status
    active_status = _normalize(scholarship_value("active_status"))
    scholarship_active = bool(scholarship_value("is_active", True))
    if active_status in {"unknown", "unverified"}:
        unknown_rules.append(
            _rule(
                "active",
                "Scholarship current status",
                active_status,
                "Current application status must be verified",
                "unknown",
                "The source data does not establish whether applications are currently open.",
            )
        )
    elif active_status in {"inactive", "expired"} or not scholarship_active:
        failed_rules.append(
            _rule(
                "active",
                "Scholarship is active",
                False,
                "Scholarship must be active",
                "failed",
                "This scholarship is no longer active.",
            )
        )
    else:
        passed_rules.append(
            _rule(
                "active",
                "Scholarship is active",
                True,
                "Scholarship must be active",
                "passed",
                "The scholarship is currently active.",
            )
        )

    # 2. Deadline
    deadline_value = scholarship_value("deadline")
    deadline = parse_date(deadline_value)
    today = date.today()
    if deadline is not None:
        if deadline < today:
            failed_rules.append(
                _rule(
                    "deadline",
                    "Application deadline",
                    str(deadline),
                    str(deadline),
                    "failed",
                    "The scholarship deadline has passed.",
                )
            )
            match_status = "expired"
            score = 0
            result = {
                "match_status": match_status,
                "match_score": score,
                "passed_rules": passed_rules,
                "failed_rules": failed_rules,
                "unknown_rules": unknown_rules,
                "warnings": warnings,
            }
            _log_debug_evaluation(student, scholarship, result)
            return result
        passed_rules.append(
            _rule(
                "deadline",
                "Application deadline",
                str(deadline),
                str(deadline),
                "passed",
                "The scholarship deadline has not passed.",
            )
        )
    else:
        unknown_rules.append(
            _rule(
                "deadline",
                "Application deadline",
                None,
                "A valid deadline is required",
                "unknown",
                "No clear deadline was provided for this scholarship.",
            )
        )

    # 3. State / domicile match
    scholarship_state = _normalize(scholarship_value("state"))
    student_state = _normalize(student_value("domicile_state") or student_value("study_state"))
    if scholarship_state in {"all india", "pan india", "all states", "india"}:
        passed_rules.append(
            _rule(
                "domicile_state",
                "Student domicile state",
                student_state,
                scholarship_state,
                "passed",
                "The scholarship is open to students across India.",
            )
        )
    elif scholarship_state and not student_state:
        unknown_rules.append(
            _rule(
                "domicile_state",
                "Student domicile state",
                student_state,
                scholarship_state,
                "unknown",
                "Student domicile state is missing, so eligibility cannot be confirmed.",
            )
        )
    elif scholarship_state and student_state:
        if student_state == scholarship_state:
            passed_rules.append(
                _rule(
                    "domicile_state",
                    "Student domicile state",
                    student_state,
                    scholarship_state,
                    "passed",
                    "The student matches the scholarship's residence requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "domicile_state",
                    "Student domicile state",
                    student_state,
                    scholarship_state,
                    "failed",
                    "The student domicile state does not match the scholarship state requirement.",
                )
            )
    elif not scholarship_state:
        unknown_rules.append(
            _rule(
                "domicile_state",
                "Student domicile state",
                student_state,
                "State requirement not specified",
                "unknown",
                "The scholarship does not specify a state requirement.",
            )
        )

    # 4. Category
    scholarship_category = _normalize(scholarship_value("category"))
    student_category = _normalize_category(student_value("category"))
    if scholarship_category:
        if _is_unmodeled_category(scholarship_category):
            unknown_rules.append(
                _rule(
                    "category",
                    "Student category",
                    student_category,
                    scholarship_category,
                    "unknown",
                    "This requirement is not represented by the saved student category fields.",
                )
            )
        elif not student_category:
            unknown_rules.append(
                _rule(
                    "category",
                    "Student category",
                    student_category,
                    scholarship_category,
                    "unknown",
                    "The scholarship requires a category, but no category is available for the student profile.",
                )
            )
        elif _category_matches(student_category, scholarship_category):
            passed_rules.append(
                _rule(
                    "category",
                    "Student category",
                    student_category,
                    scholarship_category,
                    "passed",
                    "The student category matches the scholarship category requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "category",
                    "Student category",
                    student_category,
                    scholarship_category,
                    "failed",
                    "The student category does not match the scholarship category requirement.",
                )
            )
    else:
        unknown_rules.append(
            _rule(
                "category",
                "Student category",
                student_category,
                "Category requirement was not specified",
                "unknown",
                "No category requirement was specified in the scholarship details.",
            )
        )
    additional_categories = scholarship_value("additional_category_requirements")
    if additional_categories:
        if _is_unmodeled_category(additional_categories):
            unknown_rules.append(
                _rule(
                    "additional_category",
                    "Additional scholarship category requirement",
                    student_category,
                    additional_categories,
                    "unknown",
                    "An additional category or community requirement is not represented by the saved student profile.",
                )
            )
        elif not student_category:
            unknown_rules.append(
                _rule(
                    "additional_category",
                    "Additional scholarship category requirement",
                    student_category,
                    additional_categories,
                    "unknown",
                    "The student category is missing, so this additional requirement cannot be confirmed.",
                )
            )
        elif _category_matches(student_category, additional_categories):
            passed_rules.append(
                _rule(
                    "additional_category",
                    "Additional scholarship category requirement",
                    student_category,
                    additional_categories,
                    "passed",
                    "The student category matches the additional scholarship requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "additional_category",
                    "Additional scholarship category requirement",
                    student_category,
                    additional_categories,
                    "failed",
                    "The student category does not match the additional scholarship requirement.",
                )
            )

    # 5. Education level
    scholarship_level_text = " ".join(
        str(value)
        for value in (
            scholarship_value("eligible_level"),
            scholarship_value("qualification_text"),
        )
        if value
    )
    scholarship_levels = {
        _normalize_level(level)
        for level in _education_levels(scholarship_level_text)
    }
    scholarship_level = _normalize_level(scholarship_level_text)
    student_level = _normalize_level(student_value("education_level"))
    if scholarship_levels:
        if not student_level:
            unknown_rules.append(
                _rule(
                    "education_level",
                    "Education level",
                    student_level,
                    scholarship_level_text,
                    "unknown",
                    "The student education level is missing, so this rule cannot be confirmed.",
                )
            )
        elif student_level in scholarship_levels or (
            student_level == "class 11-12"
            and student_value("education_level") in {"Class 11", "Class 12"}
            and "class 11-12" in scholarship_levels
        ):
            passed_rules.append(
                _rule(
                    "education_level",
                    "Education level",
                    student_level,
                    scholarship_level_text,
                    "passed",
                    "The student's education level matches the scholarship requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "education_level",
                    "Education level",
                    student_level,
                    scholarship_level_text,
                    "failed",
                    "The student's education level does not match the scholarship requirement.",
                )
            )
    elif scholarship_level:
        if not student_level:
            unknown_rules.append(
                _rule(
                    "education_level",
                    "Education level",
                    student_level,
                    scholarship_level_text,
                    "unknown",
                    "The student education level is missing, so this rule cannot be confirmed.",
                )
            )
        else:
            unknown_rules.append(
                _rule(
                    "education_level",
                    "Education level",
                    student_level,
                    scholarship_level_text,
                    "unknown",
                    "The stated education requirement needs verification against the student's level.",
                )
            )
    else:
        unknown_rules.append(
            _rule(
                "education_level",
                "Education level",
                student_level,
                "Education level requirement not specified",
                "unknown",
                "No education level requirement was explicitly stated.",
            )
        )
    additional_education = scholarship_value("additional_education_requirements")
    if additional_education:
        for requirement in additional_education.split(";"):
            requirement = requirement.strip()
            if not requirement:
                continue
            required_levels = {
                _normalize_level(level)
                for level in _education_levels(requirement)
            }
            if not required_levels:
                unknown_rules.append(
                    _rule(
                        "additional_education",
                        "Additional education requirement",
                        student_level,
                        requirement,
                        "unknown",
                        "This additional education requirement needs manual verification.",
                    )
                )
            elif not student_level:
                unknown_rules.append(
                    _rule(
                        "additional_education",
                        "Additional education requirement",
                        student_level,
                        requirement,
                        "unknown",
                        "The student education level is missing, so this additional requirement cannot be confirmed.",
                    )
                )
            elif student_level in required_levels:
                passed_rules.append(
                    _rule(
                        "additional_education",
                        "Additional education requirement",
                        student_level,
                        requirement,
                        "passed",
                        "The student education level matches the additional requirement.",
                    )
                )
            else:
                failed_rules.append(
                    _rule(
                        "additional_education",
                        "Additional education requirement",
                        student_level,
                        requirement,
                        "failed",
                        "The student education level does not match the additional requirement.",
                    )
                )

    # Check explicit academic-year restrictions separately from education level.
    required_years = _education_years(scholarship_level_text)
    student_years = _education_years(student_value("study_year"))

    if required_years:
        if not student_years:
            unknown_rules.append(
                _rule(
                    "study_year",
                    "Academic study year",
                    student_value("study_year"),
                    sorted(required_years),
                    "unknown",
                    "The scholarship specifies an academic year, but the student's study year is missing or unclear.",
                )
            )
        elif student_years.isdisjoint(required_years):
            failed_rules.append(
                _rule(
                    "study_year",
                    "Academic study year",
                    student_value("study_year"),
                    sorted(required_years),
                    "failed",
                    "The student's current study year does not match the scholarship's year requirement.",
                )
            )
        else:
            passed_rules.append(
                _rule(
                    "study_year",
                    "Academic study year",
                    student_value("study_year"),
                    sorted(required_years),
                    "passed",
                    "The student's study year matches the scholarship requirement.",
                )
            )

    # 6. Course requirement
    scholarship_course = scholarship_value("eligible_course")
    student_course = student_value("course")
    if scholarship_course:
        if not student_course:
            unknown_rules.append(
                _rule(
                    "course",
                    "Eligible course",
                    student_course,
                    scholarship_course,
                    "unknown",
                    "The student course is missing, so course compatibility cannot be checked.",
                )
            )
        elif _course_matches(student_course, scholarship_course):
            passed_rules.append(
                _rule(
                    "course",
                    "Eligible course",
                    student_course,
                    scholarship_course,
                    "passed",
                    "The student's course matches the scholarship's eligible course requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "course",
                    "Eligible course",
                    student_course,
                    scholarship_course,
                    "failed",
                    "The student's course does not match the scholarship's eligible course requirement.",
                )
            )
    else:
        unknown_rules.append(
            _rule(
                "course",
                "Eligible course",
                student_course,
                "Course requirement not specified",
                "unknown",
                "No course requirement was explicitly stated.",
            )
        )

    # 7. Academic score requirement
    min_percentage = scholarship_value("min_percentage")
    score = student_value("academic_score")
    if min_percentage is not None:
        if score is None:
            unknown_rules.append(
                _rule(
                    "academic_score",
                    "Academic score requirement",
                    score,
                    min_percentage,
                    "unknown",
                    "The student academic score is missing, so the minimum score requirement cannot be verified.",
                )
            )
        elif float(score) >= float(min_percentage):
            passed_rules.append(
                _rule(
                    "academic_score",
                    "Academic score requirement",
                    score,
                    min_percentage,
                    "passed",
                    "The student academic score meets the minimum requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "academic_score",
                    "Academic score requirement",
                    score,
                    min_percentage,
                    "failed",
                    "The student academic score is below the minimum required percentage.",
                )
            )
    else:
        unknown_rules.append(
            _rule(
                "academic_score",
                "Academic score requirement",
                score,
                "Minimum percentage not specified",
                "unknown",
                "No minimum percentage was explicitly stated in the scholarship.",
            )
        )

    # 8. Income requirement
    max_income = _number(scholarship_value("max_income"))
    income = student_value("annual_family_income")
    numeric_income = _number(income)
    if max_income is not None:
        if "month" in _normalize(scholarship_value("income_text")):
            unknown_rules.append(
                _rule(
                    "income",
                    "Annual family income",
                    income,
                    scholarship_value("income_text"),
                    "unknown",
                    "The scholarship uses a monthly income limit that cannot be compared directly with annual family income.",
                )
            )
        elif numeric_income is None:
            unknown_rules.append(
                _rule(
                    "income",
                    "Annual family income",
                    income,
                    max_income,
                    "unknown",
                    "The student annual family income is missing, so the income rule cannot be verified.",
                )
            )
        elif numeric_income <= max_income:
            passed_rules.append(
                _rule(
                    "income",
                    "Annual family income",
                    income,
                    max_income,
                    "passed",
                    "The student family income is within the scholarship income cap.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "income",
                    "Annual family income",
                    income,
                    max_income,
                    "failed",
                    "The student family income exceeds the scholarship income cap.",
                )
            )
    else:
        unknown_rules.append(
            _rule(
                "income",
                "Annual family income",
                income,
                "Income cap not specified",
                "unknown",
                "No maximum income was explicitly stated in the scholarship.",
            )
        )
    additional_income = scholarship_value("additional_income_requirements")
    if additional_income:
        unknown_rules.append(
            _rule(
                "additional_income",
                "Additional income requirement",
                income,
                additional_income,
                "unknown",
                "An additional source income criterion needs verification against annual family income.",
            )
        )

    # 9. Gender requirement
    scholarship_gender = _normalize(scholarship_value("gender_requirement") or scholarship_value("gender") or scholarship_value("gender_limit"))
    student_gender = _normalize(student_value("gender"))
    if scholarship_gender:
        if not student_gender:
            unknown_rules.append(
                _rule(
                    "gender",
                    "Gender requirement",
                    student_gender,
                    scholarship_gender,
                    "unknown",
                    "The student gender is missing, so this rule cannot be confirmed.",
                )
            )
        elif student_gender == scholarship_gender:
            passed_rules.append(
                _rule(
                    "gender",
                    "Gender requirement",
                    student_gender,
                    scholarship_gender,
                    "passed",
                    "The student matches the scholarship gender requirement.",
                )
            )
        else:
            failed_rules.append(
                _rule(
                    "gender",
                    "Gender requirement",
                    student_gender,
                    scholarship_gender,
                    "failed",
                    "The student gender does not match the scholarship gender requirement.",
                )
            )

    # 10. Disability requirement
    disability_flag = bool(student_value("has_disability_certificate"))
    scholarship_disability = _normalize(scholarship_value("disability_requirement") or scholarship_value("disability") or scholarship_value("disability_text"))
    if scholarship_disability:
        if disability_flag:
            passed_rules.append(
                _rule(
                    "disability",
                    "Disability requirement",
                    disability_flag,
                    scholarship_disability,
                    "passed",
                    "The student qualifies under the scholarship disability requirement.",
                )
            )
        else:
            unknown_rules.append(
                _rule(
                    "disability",
                    "Disability requirement",
                    disability_flag,
                    scholarship_disability,
                    "unknown",
                    "The scholarship includes a disability-related criterion, but the student profile does not indicate a matching disability status.",
                )
            )

    # scoring
    score = 100
    for rule in failed_rules:
        if rule["field"] in {"active", "deadline", "domicile_state", "category", "additional_category", "education_level", "additional_education", "study_year", "course", "academic_score", "income", "additional_income", "gender", "disability"}:
            score -= 25
    for rule in unknown_rules:
        if rule["field"] in {"deadline", "domicile_state", "category", "additional_category", "education_level", "additional_education", "study_year", "course", "academic_score", "income", "additional_income", "gender", "disability"}:
            score -= 10
    if student_state and scholarship_state and student_state == scholarship_state:
        score += 5
    if student_course and scholarship_course and _course_matches(student_course, scholarship_course):
        score += 5
    if scholarship_value("official_link"):
        score += 5
    score = max(0, min(100, score))

    if any(rule["field"] == "deadline" and rule["status"] == "failed" for rule in failed_rules):
        match_status = "expired"
    elif failed_rules:
        match_status = "not_matched"
    elif unknown_rules:
        match_status = "needs_verification"
    else:
        match_status = "likely_eligible"

    result = {
        "match_status": match_status,
        "match_score": score,
        "passed_rules": passed_rules,
        "failed_rules": failed_rules,
        "unknown_rules": unknown_rules,
        "warnings": warnings,
    }
    _log_debug_evaluation(student, scholarship, result)
    return result
