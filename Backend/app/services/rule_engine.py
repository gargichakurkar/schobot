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
        "sebc": "sebc",
        "sc": "sc",
        "st": "st",
        "sc st": "sc st",
        "scst": "sc st",
        "pwd": "pwd",
        "vjnt": "vjnt",
    }
    return aliases.get(category, category)


def _category_tokens(value: Any) -> set[str]:
    raw = _normalize(value)
    if not raw:
        return set()
    cleaned = re.sub(r"[^a-z0-9]+", " ", raw).strip()
    if cleaned in {
        "all",
        "all categories",
        "all students",
        "any category",
        "open to all",
        "open to all categories",
    }:
        return {"all"}

    parts = re.split(r"\s*(?:/|,|;|\bor\b|\band\b)\s*", raw)
    tokens: set[str] = set()
    for part in parts:
        p = re.sub(r"[^a-z0-9]+", " ", part).strip()
        if not p:
            continue
        if p in {"all", "all categories", "all students", "any category", "open to all"}:
            tokens.add("all")
        elif p == "sc":
            tokens.add("sc")
        elif p == "st":
            tokens.add("st")
        elif p in {"sc st", "scst", "sc and st", "sc or st"}:
            tokens.add("sc")
            tokens.add("st")
        elif p == "sebc":
            tokens.add("sebc")
            tokens.add("obc")
        elif p == "obc":
            tokens.add("obc")
        elif p == "ews":
            tokens.add("ews")
        elif p in {"vjnt", "vj", "nt", "vj/nt"}:
            tokens.add("vjnt")
        elif p == "sbc":
            tokens.add("sbc")
        elif p in {"pwd", "ph", "handicapped", "differently abled", "divyang"}:
            tokens.add("pwd")
        elif p in {"open", "general"}:
            tokens.add("general")
        else:
            tokens.add(p)
    return tokens


def _category_matches(student_category: Any, scholarship_category: Any) -> bool:
    scholarship_tokens = _category_tokens(scholarship_category)
    if not scholarship_tokens:
        return False
    if "all" in scholarship_tokens:
        return True

    student_tokens = _category_tokens(student_category)
    if not student_tokens:
        return False

    return bool(student_tokens.intersection(scholarship_tokens))


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
    text = _normalize(value)
    if not text:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", text).strip()
    mapping = {
        "ug": "undergraduate",
        "undergrad": "undergraduate",
        "undergraduate": "undergraduate",
        "graduation": "undergraduate",
        "bachelor": "undergraduate",
        "bachelors": "undergraduate",
        "bachelor s": "undergraduate",
        "bachelor degree": "undergraduate",
        "bachelor s degree": "undergraduate",
        "bachelors degree": "undergraduate",
        "pg": "postgraduate",
        "postgrad": "postgraduate",
        "post graduate": "postgraduate",
        "postgraduate": "postgraduate",
        "post graduation": "postgraduate",
        "master": "postgraduate",
        "masters": "postgraduate",
        "master s": "postgraduate",
        "master degree": "postgraduate",
        "master s degree": "postgraduate",
        "masters degree": "postgraduate",
        "postgraduate degree": "postgraduate",
        "mba": "postgraduate",
        "b e": "undergraduate",
        "diploma": "diploma",
        "iti": "diploma",
        "industrial training institute": "diploma",
        "polytechnic": "diploma",
        "school": "school",
        "school level": "school",
        "school level education": "school",
        "school education": "school",
        "class 9": "class 9",
        "class 10": "class 10",
        "10th": "class 10",
        "class 11": "class 11-12",
        "class 11 12": "class 11-12",
        "class 11 12th": "class 11-12",
        "class 12": "class 11-12",
        "11th": "class 11-12",
        "12th": "class 11-12",
        "phd": "phd",
        "doctorate": "phd",
    }
    return mapping.get(normalized, normalized)


def _education_levels(value: Any) -> set[str]:
    text = _normalize(value)
    exact_level = _normalize_level(text)
    if exact_level == "school":
        return {"class 9", "class 10", "class 11-12"}
    if exact_level in {
        "undergraduate",
        "postgraduate",
        "diploma",
        "phd",
        "class 9",
        "class 10",
        "class 11-12",
    }:
        return {exact_level}

    levels: set[str] = set()

    if re.search(
        r"\b(?:1st|class\s*1)\s*(?:to|-)\s*(?:10th|class\s*10)\b",
        text,
    ):
        levels.update({"class 9", "class 10"})

    if re.search(
        r"\b(?:class(?:es)?\s*)?11\s*(?:and|&|or|-)\s*(?:class(?:es)?\s*)?12\b"
        r"|\b11th\s*(?:and|&|or)\s*12th\b",
        text,
    ):
        levels.add("class 11-12")
    elif re.search(r"\b(?:class\s*11|11th|fyjc|syjc)\b", text):
        levels.add("class 11-12")
    elif re.search(r"\b(?:class\s*12|12th|hsc)\b", text):
        levels.add("class 11-12")

    is_postgraduate = bool(
        re.search(
            r"\b(?:post[\s-]?graduate|post[\s-]?graduation|postgrad|pg|"
            r"master(?:'s|s)?|mba|ph\.?d|doctorate)\b",
            text,
        )
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
        r"\b(?:ug|undergraduate|under[\s-]?graduation|undergrad|graduation|"
        r"bachelor(?:'s|s)?(?:\s+degree)?|b\.?tech|b\.?sc|b\.?e\.?)\b",
        text,
    ):
        levels.add("undergraduate")
    elif re.search(r"\bdegree\s+(?:or|and)\s+diploma\b|\bdiploma\s+(?:or|and)\s+degree\b", text):
        levels.add("undergraduate")

    if re.search(
        r"\b(?:diploma|polytechnic|iti|industrial training institute)\b",
        text,
    ):
        levels.add("diploma")

    if re.search(r"\bschool[\s-]?level(?:\s+education)?\b", text):
        levels.update({"class 9", "class 10", "class 11-12"})

    return levels


def _score_scale(value: Any) -> float | None:
    text = _normalize(value)
    match = re.search(
        r"(?:\b(?:out\s+of|on|scale\s+of)\s+(?:a\s+)?|/\s*)"
        r"(\d+(?:\.\d+)?)\b"
        r"|\b(\d+(?:\.\d+)?)\s*[- ]?point(?:s)?(?:\s+scale)?\b",
        text,
    )
    if not match:
        return None
    return _number(match.group(1) or match.group(2))


def _cgpa_requirement(minimum_marks_text: Any) -> tuple[float, float | None] | None:
    text = _normalize(minimum_marks_text)
    match = re.search(
        r"\bcgpa\b[^0-9]{0,30}(\d+(?:\.\d+)?)"
        r"|(\d+(?:\.\d+)?)\s*cgpa\b",
        text,
    )
    if not match:
        return None
    threshold = _number(match.group(1) or match.group(2))
    if threshold is None:
        return None
    return threshold, _score_scale(text)


def _percentage_requirement(
    minimum_marks_text: Any,
) -> float | None:
    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:%|\bpercent(?:age)?\b)",
        _normalize(minimum_marks_text),
    )
    return _number(match.group(1)) if match else None


def _special_requirement_text(scholarship: Any) -> str:
    fields = (
        "eligibility_details",
        "qualification_text",
        "additional_category_requirements",
        "additional_education_requirements",
        "minimum_marks_text",
        "disability_requirement",
        "disability",
        "disability_text",
    )
    return " ".join(
        str(value)
        for field in fields
        if (value := _get_value(scholarship, field))
    ).casefold()


def _append_boolean_rule(
    field: str,
    label: str,
    student_value: Any,
    expected: bool,
    requirement: str,
    passed_rules: list[dict],
    failed_rules: list[dict],
    unknown_rules: list[dict],
) -> None:
    if student_value is None:
        status = "unknown"
        message = f"The student {label.lower()} is missing, so this requirement cannot be confirmed."
    elif student_value is expected:
        status = "passed"
        message = f"The student meets the {label.lower()} requirement."
    else:
        status = "failed"
        message = f"The student does not meet the {label.lower()} requirement."

    rule = _rule(field, label, student_value, requirement, status, message)
    {"passed": passed_rules, "failed": failed_rules, "unknown": unknown_rules}[
        status
    ].append(rule)


def _disability_percentage_requirement(text: str) -> float | None:
    patterns = (
        r"\b(?:minimum|at least|not less than)\s*(\d+(?:\.\d+)?)\s*%\s*"
        r"(?:benchmark\s+)?disabilit\w*\b",
        r"\bdisabilit\w*\b.{0,30}\b(?:minimum|at least|of)\s*"
        r"(\d+(?:\.\d+)?)\s*%",
        r"\b(\d+(?:\.\d+)?)\s*%\s*(?:or more|and above).{0,30}\bdisabilit\w*\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _number(match.group(1))
    return None


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
    structured_level = scholarship_value("eligible_level")
    qualification_text = scholarship_value("qualification_text")
    scholarship_level_text = " ".join(
        str(value) for value in (structured_level, qualification_text) if value
    )
    scholarship_levels = _education_levels(structured_level)
    if not scholarship_levels:
        scholarship_levels = _education_levels(qualification_text)
    student_level = _normalize_level(student_value("education_level"))
    student_levels = _education_levels(student_value("education_level"))
    if not student_levels and student_level:
        student_levels = {student_level}
    if scholarship_levels:
        if not student_levels:
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
        elif not student_levels.isdisjoint(scholarship_levels):
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
    elif scholarship_level_text:
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
            elif not student_levels:
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
            elif not student_levels.isdisjoint(required_levels):
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
    year_requirement_text = " ".join(
        str(value)
        for value in (
            scholarship_value("year_text"),
            structured_level,
            qualification_text,
        )
        if value
    )
    required_years = _education_years(year_requirement_text)
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
    score = _number(student_value("academic_score"))
    score_type = _normalize(student_value("score_type"))
    minimum_marks_text = scholarship_value("minimum_marks_text")
    cgpa_requirement = _cgpa_requirement(minimum_marks_text)
    percentage_requirement = _number(scholarship_value("min_percentage"))
    if percentage_requirement is None:
        percentage_requirement = _percentage_requirement(minimum_marks_text)

    def add_academic_rule(requirement: Any, status: str, message: str) -> None:
        rule = _rule(
            "academic_score",
            "Academic score requirement",
            score,
            requirement,
            status,
            message,
        )
        {"passed": passed_rules, "failed": failed_rules, "unknown": unknown_rules}[
            status
        ].append(rule)

    if score is None:
        add_academic_rule(
            cgpa_requirement or percentage_requirement,
            "unknown",
            "The student academic score is missing, so the score requirement cannot be verified.",
        )
    elif re.search(r"\bcgpa\b", score_type):
        if cgpa_requirement is not None:
            cgpa_threshold, required_scale = cgpa_requirement
            student_scale = _score_scale(score_type)
            requirement = {
                "minimum": cgpa_threshold,
                "unit": "CGPA",
                "scale": required_scale,
            }
            if (
                student_scale is None
                or required_scale is None
                or student_scale != required_scale
            ):
                add_academic_rule(
                    requirement,
                    "unknown",
                    "The student and scholarship CGPA scales are missing or incompatible, so the score cannot be compared.",
                )
            elif score >= cgpa_threshold:
                add_academic_rule(
                    requirement,
                    "passed",
                    "The student CGPA meets the scholarship's CGPA requirement on the same scale.",
                )
            else:
                add_academic_rule(
                    requirement,
                    "failed",
                    "The student CGPA is below the scholarship's CGPA requirement.",
                )
        elif percentage_requirement is not None:
            add_academic_rule(
                {"minimum": percentage_requirement, "unit": "percentage"},
                "unknown",
                "A CGPA cannot be compared with the percentage requirement without a verified conversion.",
            )
        else:
            add_academic_rule(
                "Minimum CGPA requirement not specified",
                "unknown",
                "No explicit CGPA requirement was stated in the scholarship.",
            )
    elif re.search(r"\bpercent(?:age)?\b|%", score_type):
        if percentage_requirement is not None:
            requirement = {"minimum": percentage_requirement, "unit": "percentage"}
            if score >= percentage_requirement:
                add_academic_rule(
                    requirement,
                    "passed",
                    "The student percentage meets the minimum requirement.",
                )
            else:
                add_academic_rule(
                    requirement,
                    "failed",
                    "The student percentage is below the minimum required percentage.",
                )
        elif cgpa_requirement is not None:
            add_academic_rule(
                {
                    "minimum": cgpa_requirement[0],
                    "unit": "CGPA",
                    "scale": cgpa_requirement[1],
                },
                "unknown",
                "A percentage cannot be compared with the scholarship's CGPA requirement.",
            )
        else:
            add_academic_rule(
                "Minimum percentage requirement not specified",
                "unknown",
                "No minimum percentage was explicitly stated in the scholarship.",
            )
    else:
        add_academic_rule(
            cgpa_requirement or percentage_requirement,
            "unknown",
            "The student score type is missing or unsupported, so the score requirement cannot be compared.",
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

    special_text = _special_requirement_text(scholarship)

    disability_requirement = (
        scholarship_value("disability_requirement")
        or scholarship_value("disability")
        or scholarship_value("disability_text")
    )
    no_disability_restriction = re.search(
        r"\b(?:no|without)\s+(?:specific\s+)?disability\s+(?:requirement|restriction)\b",
        special_text,
    )
    disability_related = bool(
        disability_requirement
        or (
            re.search(r"\b(?:disabilit\w*|disabled|udid)\b", special_text)
            and not no_disability_restriction
        )
    )
    if disability_related:
        disability_threshold = _disability_percentage_requirement(special_text)
        certificate_required = bool(
            re.search(
                r"\b(?:valid\s+)?disability\s+certificate\b.{0,30}"
                r"\b(?:required|mandatory|must|shall)\b"
                r"|\b(?:must|shall|need(?:s)? to|require(?:s|d)?)\b.{0,40}"
                r"\b(?:valid\s+)?disability\s+certificate\b",
                special_text,
            )
        )
        udid_required = bool(
            re.search(r"\budid\b.{0,30}\b(?:required|mandatory|must|shall)\b", special_text)
            or re.search(r"\b(?:must|shall|need(?:s)? to|require(?:s|d)?)\b.{0,30}\budid\b", special_text)
        )
        specific_disability_rule = False

        if disability_threshold is not None:
            specific_disability_rule = True
            percentage = _number(student_value("disability_percentage"))
            requirement = f"At least {disability_threshold}% disability"
            if percentage is None:
                status = "unknown"
                message = "The student disability percentage is missing, so this threshold cannot be confirmed."
            elif percentage >= disability_threshold:
                status = "passed"
                message = "The student disability percentage meets the stated threshold."
            else:
                status = "failed"
                message = "The student disability percentage is below the stated threshold."
            rule = _rule(
                "disability_percentage",
                "Disability percentage",
                percentage,
                requirement,
                status,
                message,
            )
            {"passed": passed_rules, "failed": failed_rules, "unknown": unknown_rules}[
                status
            ].append(rule)

        if certificate_required:
            specific_disability_rule = True
            requires_valid_certificate = bool(
                re.search(r"\bvalid\b.{0,25}\bdisability\s+certificate\b", special_text)
            )
            certificate_value = student_value(
                "has_valid_disability_certificate"
                if requires_valid_certificate
                else "has_disability_certificate"
            )
            _append_boolean_rule(
                "has_valid_disability_certificate"
                if requires_valid_certificate
                else "has_disability_certificate",
                "Valid disability certificate"
                if requires_valid_certificate
                else "Disability certificate",
                certificate_value,
                True,
                "A disability certificate is explicitly required.",
                passed_rules,
                failed_rules,
                unknown_rules,
            )

        if udid_required:
            specific_disability_rule = True
            _append_boolean_rule(
                "has_udid",
                "UDID",
                student_value("has_udid"),
                True,
                "A UDID is explicitly required.",
                passed_rules,
                failed_rules,
                unknown_rules,
            )

        if not specific_disability_rule:
            disability_details = {
                "percentage": student_value("disability_percentage"),
                "has_valid_certificate": student_value(
                    "has_valid_disability_certificate"
                ),
                "has_udid": student_value("has_udid"),
            }
            unknown_rules.append(
                _rule(
                    "disability",
                    "Disability requirement",
                    disability_details,
                    disability_requirement or "Disability-specific requirement",
                    "unknown",
                    "The scholarship mentions disability but does not state a specific threshold or document requirement.",
                )
            )

    orphan_requirement = re.search(r"\borphan(?:s|ed)?\b", special_text)
    if orphan_requirement:
        requires_orphan = not bool(
            re.search(r"\b(?:non[-\s]?orphan|not\s+(?:an?\s+)?orphan)\b", special_text)
        )
        _append_boolean_rule(
            "is_orphan",
            "Orphan status",
            student_value("is_orphan"),
            requires_orphan,
            "The scholarship explicitly states an orphan-status condition.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    parent_covid_requirement = (
        "covid" in special_text
        and re.search(r"\b(?:parent|father|mother)\b", special_text)
        and re.search(r"\b(?:death|died|deceased|demise)\b", special_text)
    )
    if parent_covid_requirement:
        _append_boolean_rule(
            "parent_death_due_to_covid",
            "Parent death due to COVID",
            student_value("parent_death_due_to_covid"),
            True,
            "The scholarship explicitly requires a parent's death due to COVID.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    parent_martyr_requirement = (
        re.search(r"\b(?:parent|father|mother|ward)\b", special_text)
        and re.search(r"\b(?:martyr|martyred|killed)\b", special_text)
        and re.search(r"\b(?:armed forces|army|military|defence|defense)\b", special_text)
    )
    if parent_martyr_requirement:
        _append_boolean_rule(
            "parent_martyred_armed_forces",
            "Parent martyred in the armed forces",
            student_value("parent_martyred_armed_forces"),
            True,
            "The scholarship explicitly requires a parent martyred in the armed forces.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    rpf_requirement = bool(
        re.search(r"\b(?:rpf|rpsf|railway protection force)\b", special_text)
        and re.search(r"\b(?:dependent|dependant|ward|child|children)\b", special_text)
    )
    if rpf_requirement:
        _append_boolean_rule(
            "is_dependent_of_rpf_rpsf",
            "RPF/RPSF dependent status",
            student_value("is_dependent_of_rpf_rpsf"),
            True,
            "The scholarship explicitly requires an RPF/RPSF dependent.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    if re.search(r"\b(?:rpf|rpsf|railway protection force)\b", special_text):
        required_service_categories = {
            value
            for value in ("serving", "retired", "deceased", "martyred")
            if re.search(rf"\b{value}\b", special_text)
        }
        if required_service_categories:
            service_category = _normalize(student_value("parent_service_category"))
            student_service_categories = {
                category
                for category in ("serving", "retired", "deceased", "martyred")
                if re.search(rf"\b{category}\b", service_category)
            }
            if not service_category:
                status = "unknown"
                message = "The student's parent service category is missing, so this requirement cannot be confirmed."
            elif not student_service_categories.isdisjoint(
                required_service_categories
            ):
                status = "passed"
                message = "The student's parent service category matches the stated requirement."
            else:
                status = "failed"
                message = "The student's parent service category does not match the stated requirement."
            rule = _rule(
                "parent_service_category",
                "Parent service category",
                service_category or None,
                sorted(required_service_categories),
                status,
                message,
            )
            {"passed": passed_rules, "failed": failed_rules, "unknown": unknown_rules}[
                status
            ].append(rule)

    previous_year_pass_requirement = (
        re.search(r"\b(?:previous|preceding|last)\s+(?:academic\s+)?year\b", special_text)
        and re.search(r"\bpassed\b", special_text)
    )
    if previous_year_pass_requirement:
        _append_boolean_rule(
            "previous_year_passed",
            "Previous year passed",
            student_value("previous_year_passed"),
            True,
            "The scholarship explicitly requires passing the previous year.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    no_other_scholarship_requirement = re.search(
        r"\b(?:not|no|cannot|must\s+not|shall\s+not|should\s+not)\b.{0,50}"
        r"\b(?:receive|receiving|avail|availing)\b.{0,40}"
        r"\b(?:another|other)\s+scholarship\b",
        special_text,
    )
    if no_other_scholarship_requirement:
        _append_boolean_rule(
            "receives_other_scholarship",
            "Other scholarship status",
            student_value("receives_other_scholarship"),
            False,
            "The scholarship explicitly requires that the student not receive another scholarship.",
            passed_rules,
            failed_rules,
            unknown_rules,
        )

    # scoring
    score = 100
    for rule in failed_rules:
        if rule["field"] in {
            "active", "deadline", "domicile_state", "category", "additional_category",
            "education_level", "additional_education", "study_year", "course",
            "academic_score", "income", "additional_income", "gender", "disability",
            "disability_percentage", "has_valid_disability_certificate", "has_disability_certificate",
            "has_udid", "is_orphan", "parent_death_due_to_covid",
            "parent_martyred_armed_forces", "is_dependent_of_rpf_rpsf",
            "parent_service_category", "previous_year_passed", "receives_other_scholarship",
        }:
            score -= 25
    for rule in unknown_rules:
        if rule["field"] in {
            "deadline", "domicile_state", "category", "additional_category",
            "education_level", "additional_education", "study_year", "course",
            "academic_score", "income", "additional_income", "gender", "disability",
            "disability_percentage", "has_valid_disability_certificate", "has_disability_certificate",
            "has_udid", "is_orphan", "parent_death_due_to_covid",
            "parent_martyred_armed_forces", "is_dependent_of_rpf_rpsf",
            "parent_service_category", "previous_year_passed", "receives_other_scholarship",
        }:
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
