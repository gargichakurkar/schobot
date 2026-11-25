import pytest

from app.services.rule_engine import evaluate_eligibility


def build_student(**overrides):
    base = {
        "id": "11111111-1111-4111-8111-111111111111",
        "full_name": "Asha Verma",
        "email": "asha@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "ABC College",
        "academic_score": 92.0,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Female",
        "has_disability_certificate": False,
        "annual_family_income": 180000,
        "has_income_certificate": True,
        "profile_completed": True,
    }
    base.update(overrides)
    return base


def build_scholarship(**overrides):
    base = {
        "id": "22222222-2222-4222-8222-222222222222",
        "dataset_id": "SCH-100",
        "scholarship_name": "Merit Support Grant",
        "state": "Maharashtra",
        "category": "General",
        "income_text": "Annual income should be less than 250000",
        "qualification_text": "Undergraduate students",
        "description": "For undergraduate students with strong academics.",
        "official_link": "https://example.com/scholarship",
        "scholarship_type": "Merit",
        "max_income": 250000,
        "min_percentage": 75,
        "eligible_level": "Undergraduate",
        "eligible_course": "B.Tech",
        "deadline": "2035-12-31",
        "is_active": True,
    }
    base.update(overrides)
    return base


def test_matching_student_is_likely_eligible():
    result = evaluate_eligibility(build_student(), build_scholarship())
    assert result["match_status"] == "likely_eligible"
    assert result["match_score"] >= 70


def test_sebc_student_matches_obc_requirement():
    result = evaluate_eligibility(
        build_student(category="SEBC"),
        build_scholarship(category="OBC"),
    )
    assert result["match_status"] == "likely_eligible"


def test_undergraduate_profile_matches_all_india_graduation_scholarship():
    result = evaluate_eligibility(
        build_student(education_level="Graduation"),
        build_scholarship(state="All India", eligible_level="Graduation"),
    )
    assert result["match_status"] == "likely_eligible"


def test_class_12_profile_matches_class_11_12_requirement():
    result = evaluate_eligibility(
        build_student(education_level="Class 12"),
        build_scholarship(state="All India", eligible_level="Class 11-12"),
    )
    assert result["match_status"] == "likely_eligible"


def test_class_11_profile_matches_class_11_12_requirement():
    result = evaluate_eligibility(
        build_student(education_level="Class 11"),
        build_scholarship(state="All India", eligible_level="Class 11-12"),
    )
    assert result["match_status"] == "likely_eligible"


def test_class_9_does_not_match_class_11_12_requirement():
    result = evaluate_eligibility(
        build_student(education_level="Class 9"),
        build_scholarship(state="All India", eligible_level="Class 11-12"),
    )
    assert result["match_status"] == "not_matched"


def test_sc_st_profile_matches_sc_or_st_requirements():
    for scholarship_category in ("SC", "ST", "SC/ST"):
        result = evaluate_eligibility(
            build_student(category="SC/ST"),
            build_scholarship(category=scholarship_category),
        )
        assert result["match_status"] == "likely_eligible"


def test_sc_student_does_not_match_st_exclusive_scholarship():
    result = evaluate_eligibility(
        build_student(category="SC"),
        build_scholarship(category="ST"),
    )
    assert result["match_status"] == "not_matched"


def test_st_student_does_not_match_sc_exclusive_scholarship():
    result = evaluate_eligibility(
        build_student(category="ST"),
        build_scholarship(category="SC"),
    )
    assert result["match_status"] == "not_matched"


def test_sc_student_matches_sc_and_sc_st_scholarships():
    for scholarship_category in ("SC", "SC/ST", "SC, ST", "SC or ST"):
        result = evaluate_eligibility(
            build_student(category="SC"),
            build_scholarship(category=scholarship_category),
        )
        assert result["match_status"] == "likely_eligible"


def test_st_student_matches_st_and_sc_st_scholarships():
    for scholarship_category in ("ST", "SC/ST", "SC, ST", "SC or ST"):
        result = evaluate_eligibility(
            build_student(category="ST"),
            build_scholarship(category=scholarship_category),
        )
        assert result["match_status"] == "likely_eligible"


def test_ews_and_obc_distinction():
    # EWS student should not match OBC scholarship
    result = evaluate_eligibility(
        build_student(category="EWS"),
        build_scholarship(category="OBC"),
    )
    assert result["match_status"] == "not_matched"

    # OBC student should not match EWS scholarship
    result = evaluate_eligibility(
        build_student(category="OBC"),
        build_scholarship(category="EWS"),
    )
    assert result["match_status"] == "not_matched"


def test_vjnt_and_pwd_categories_match_exact_requirements():
    for category in ("VJNT", "PWD"):
        result = evaluate_eligibility(
            build_student(category=category),
            build_scholarship(category=category),
        )
        assert result["match_status"] == "likely_eligible"



def test_all_students_course_requirement_is_not_a_mismatch():
    result = evaluate_eligibility(
        build_student(),
        build_scholarship(eligible_course="All students"),
    )
    assert result["match_status"] == "likely_eligible"


def test_currency_formatted_income_is_compared_numerically():
    result = evaluate_eligibility(
        build_student(annual_family_income="₹1,80,000"),
        build_scholarship(max_income=250000),
    )
    assert result["match_status"] == "likely_eligible"


def test_invalid_income_is_needs_verification_not_a_failure():
    result = evaluate_eligibility(
        build_student(annual_family_income="not provided"),
        build_scholarship(max_income=250000),
    )
    assert result["match_status"] == "needs_verification"
    assert any(rule["field"] == "income" for rule in result["unknown_rules"])


def test_income_too_high_returns_not_matched():
    result = evaluate_eligibility(
        build_student(annual_family_income=500000),
        build_scholarship(max_income=250000),
    )
    assert result["match_status"] == "not_matched"
    assert any(rule["field"] == "income" and rule["status"] == "failed" for rule in result["failed_rules"])


def test_marks_too_low_returns_not_matched():
    result = evaluate_eligibility(
        build_student(academic_score=60),
        build_scholarship(min_percentage=75),
    )
    assert result["match_status"] == "not_matched"
    assert any(rule["field"] == "academic_score" and rule["status"] == "failed" for rule in result["failed_rules"])


def test_cgpa_is_unknown_against_percentage_threshold_without_conversion():
    result = evaluate_eligibility(
        build_student(academic_score=9.67, score_type="CGPA"),
        build_scholarship(min_percentage=60),
    )

    assert result["match_status"] == "needs_verification"
    assert any(
        rule["field"] == "academic_score" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


def test_cgpa_compares_when_both_explicit_scales_match():
    result = evaluate_eligibility(
        build_student(academic_score=9.67, score_type="CGPA out of 10"),
        build_scholarship(
            min_percentage=None,
            minimum_marks_text="Minimum CGPA 8.0 on a 10-point scale",
        ),
    )

    assert any(
        rule["field"] == "academic_score" and rule["status"] == "passed"
        for rule in result["passed_rules"]
    )


def test_percentage_score_keeps_comparing_to_percentage_requirement():
    result = evaluate_eligibility(
        build_student(academic_score=80, score_type="Percentage"),
        build_scholarship(min_percentage=60),
    )

    assert any(
        rule["field"] == "academic_score" and rule["status"] == "passed"
        for rule in result["passed_rules"]
    )


def test_missing_category_when_required_returns_needs_verification():
    result = evaluate_eligibility(
        build_student(category=None),
        build_scholarship(category="General"),
    )
    assert result["match_status"] == "needs_verification"
    assert any(rule["field"] == "category" and rule["status"] == "unknown" for rule in result["unknown_rules"])


def test_unclear_qualification_returns_needs_verification():
    result = evaluate_eligibility(
        build_student(education_level=None),
        build_scholarship(eligible_level="Undergraduate"),
    )
    assert result["match_status"] == "needs_verification"
    assert any(rule["field"] == "education_level" and rule["status"] == "unknown" for rule in result["unknown_rules"])


def test_undergraduate_profile_matches_graduation_requirement():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate"),
        build_scholarship(eligible_level="Graduation"),
    )

    assert any(
        rule["field"] == "education_level" and rule["status"] == "passed"
        for rule in result["passed_rules"]
    )


def test_undergraduate_does_not_match_postgraduate_word_in_long_description():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate"),
        build_scholarship(
            eligible_level="Undergraduate",
            qualification_text=(
                "Undergraduate students must not already hold a postgraduate degree."
            ),
        ),
    )

    assert not any(
        rule["field"] == "education_level" and rule["status"] == "failed"
        for rule in result["failed_rules"]
    )


def test_expired_scholarship_returns_expired():
    result = evaluate_eligibility(
        build_student(),
        build_scholarship(deadline="2020-01-01"),
    )
    assert result["match_status"] == "expired"


def test_unknown_current_status_needs_verification():
    result = evaluate_eligibility(
        build_student(),
        build_scholarship(is_active=False, active_status="unknown"),
    )
    assert result["match_status"] == "needs_verification"
    assert any(
        rule["field"] == "active" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )
    assert not any(rule["field"] == "active" for rule in result["failed_rules"])


def test_unmodeled_worker_family_category_needs_verification():
    result = evaluate_eligibility(
        build_student(category="General"),
        build_scholarship(category="Wards of Beedi and Cine workers"),
    )
    assert result["match_status"] == "needs_verification"
    assert any(
        rule["field"] == "category" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


def test_multiple_education_requirements_match_any_explicit_level():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate"),
        build_scholarship(
            eligible_level="Class 1 to Class 10, Graduation, Post-Graduation, PhD",
        ),
    )
    assert any(
        rule["field"] == "education_level" and rule["status"] == "passed"
        for rule in result["passed_rules"]
    )


def test_monthly_income_limit_is_not_compared_to_annual_profile_income():
    result = evaluate_eligibility(
        build_student(annual_family_income=50_000),
        build_scholarship(
            max_income=10_000,
            income_text="Monthly income not exceeding Rs. 10,000",
        ),
    )
    assert result["match_status"] == "needs_verification"
    assert any(
        rule["field"] == "income" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )
    assert not any(rule["field"] == "income" for rule in result["passed_rules"])


def test_additional_income_requirement_blocks_unverified_eligibility():
    result = evaluate_eligibility(
        build_student(),
        build_scholarship(
            additional_income_requirements="Monthly income not exceeding Rs. 10,000",
        ),
    )
    assert result["match_status"] == "needs_verification"
    assert any(
        rule["field"] == "additional_income" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


def test_missing_disability_value_remains_unknown_not_false():
    result = evaluate_eligibility(
        build_student(has_disability_certificate=None),
        build_scholarship(disability_requirement="Disability certificate required"),
    )

    disability_rule = next(
        rule
        for rule in result["unknown_rules"]
        if rule["field"] == "has_disability_certificate"
    )
    assert disability_rule["student_value"] is None
    assert result["match_status"] == "needs_verification"


def test_null_disability_details_are_unknown_for_disability_specific_scholarship():
    result = evaluate_eligibility(
        build_student(
            disability_percentage=None,
            has_disability_certificate=None,
            has_valid_disability_certificate=None,
            has_udid=None,
        ),
        build_scholarship(
            eligibility_details="Scholarship is for students with disabilities."
        ),
    )

    assert any(
        rule["field"] == "disability" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


def test_false_disability_certificate_fails_when_valid_certificate_is_mandatory():
    result = evaluate_eligibility(
        build_student(has_valid_disability_certificate=False),
        build_scholarship(
            eligibility_details="Applicants must have a valid disability certificate."
        ),
    )

    assert any(
        rule["field"] == "has_valid_disability_certificate"
        and rule["status"] == "failed"
        for rule in result["failed_rules"]
    )


def test_null_orphan_status_is_unknown_for_orphan_requirement():
    result = evaluate_eligibility(
        build_student(is_orphan=None),
        build_scholarship(eligibility_details="Applicants must be orphans."),
    )

    assert any(
        rule["field"] == "is_orphan" and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


@pytest.mark.parametrize(
    ("field", "requirement"),
    [
        (
            "parent_death_due_to_covid",
            "Applicants whose parent died due to COVID-19 are eligible.",
        ),
        (
            "parent_martyred_armed_forces",
            "Applicants whose parent was martyred in the armed forces are eligible.",
        ),
        (
            "is_dependent_of_rpf_rpsf",
            "Applicants must be dependent wards of RPF/RPSF staff.",
        ),
        (
            "parent_service_category",
            "Wards of retired RPF staff are eligible.",
        ),
        (
            "previous_year_passed",
            "Applicants must have passed the previous academic year.",
        ),
        (
            "receives_other_scholarship",
            "Students must not receive any other scholarship.",
        ),
        (
            "has_udid",
            "A valid UDID is mandatory.",
        ),
        (
            "disability_percentage",
            "Applicants must have at least 40% disability.",
        ),
    ],
)
def test_missing_special_eligibility_fields_remain_unknown(field, requirement):
    result = evaluate_eligibility(
        build_student(**{field: None}),
        build_scholarship(eligibility_details=requirement),
    )

    assert any(
        rule["field"] == field and rule["status"] == "unknown"
        for rule in result["unknown_rules"]
    )


def test_third_year_student_does_not_match_first_year_only_scholarship():
    result = evaluate_eligibility(
        build_student(study_year="3rd Year"),
        build_scholarship(
            eligible_level="Undergraduate",
            qualification_text="First-year Undergraduate students",
        ),
    )
    assert result["match_status"] == "not_matched"
    assert any(
        rule["field"] == "study_year" and rule["status"] == "failed"
        for rule in result["failed_rules"]
    )


def test_undergraduate_student_does_not_match_postgraduate_degree_scholarship():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate"),
        build_scholarship(
            eligible_level="Postgraduate",
            qualification_text="First year of a recognized full-time postgraduate degree",
        ),
    )
    assert result["match_status"] == "not_matched"
    assert any(
        rule["field"] == "education_level" and rule["status"] == "failed"
        for rule in result["failed_rules"]
    )


def test_broad_post_matric_requirement_does_not_reject_undergraduate_student():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate", study_year="3rd Year"),
        build_scholarship(
            eligible_level="Post Matric",
            qualification_text="Students pursuing post-matric education",
        ),
    )
    assert not any(
        rule["field"] == "education_level" and rule["status"] == "failed"
        for rule in result["failed_rules"]
    )
    assert result["match_status"] == "needs_verification"


def test_pragati_first_year_requirement_rejects_third_year_student():
    result = evaluate_eligibility(
        build_student(study_year="3rd Year"),
        build_scholarship(
            scholarship_name="Pragati Scholarship Scheme for Girl Students",
            eligible_level="1st year Degree or Diploma in Engineering or Technology",
            qualification_text="1st year Degree or Diploma in Engineering or Technology",
        ),
    )
    assert result["match_status"] == "not_matched"
    assert any(r["field"] == "study_year" and r["status"] == "failed" for r in result["failed_rules"])


def test_national_postgraduate_scholarship_rejects_undergraduate():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate"),
        build_scholarship(
            scholarship_name="National Scholarship for Post Graduate Studies",
            eligible_level="First year of a recognized full-time postgraduate degree",
            qualification_text="First year of a recognized full-time postgraduate degree",
        ),
    )
    assert result["match_status"] == "not_matched"
    assert any(r["field"] == "education_level" and r["status"] == "failed" for r in result["failed_rules"])


def test_maharashtra_post_matric_class_11_to_phd_includes_undergraduate():
    result = evaluate_eligibility(
        build_student(education_level="Undergraduate", study_year="3rd Year"),
        build_scholarship(
            scholarship_name="Government of India Post-Matric Scholarship (Maharashtra)",
            eligible_level="Post-Matriculation courses (Class 11 to PhD)",
            qualification_text="Post-Matriculation courses (Class 11 to PhD)",
        ),
    )
    assert not any(r["field"] == "education_level" and r["status"] == "failed" for r in result["failed_rules"])
    assert not any(r["field"] == "study_year" and r["status"] == "failed" for r in result["failed_rules"])
