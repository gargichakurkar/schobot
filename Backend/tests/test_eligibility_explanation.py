from datetime import datetime, timezone
import pytest
from app.core.database import get_db
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.services.rule_engine import evaluate_eligibility


def test_scenario_1_fully_eligible_student(isolated_client):
    client = isolated_client
    db = next(isolated_client.app.dependency_overrides[get_db]())

    scholarship = Scholarship(
        scholarship_name="Maharashtra Merit Support Grant",
        provider="Govt of Maharashtra",
        state="Maharashtra",
        category="General",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=300000,
        min_percentage=75,
        is_active=True,
        active_status="active",
        deadline=datetime(2035, 12, 31, tzinfo=timezone.utc),
    )
    db.add(scholarship)
    db.commit()

    student_payload = {
        "full_name": "Aarav Sharma",
        "email": "aarav@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "Pune Engineering College",
        "academic_score": 88,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Male",
        "annual_family_income": 200000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    create_res = client.post("/api/profile/submit-and-recommend", json=student_payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["student"]["id"]

    # Check eligibility endpoint
    res = client.get(f"/api/scholarships/{scholarship.id}/eligibility/{student_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "likely_eligible"
    assert data["match_score"] >= 70
    assert len(data["failed_rules"]) == 0
    passed_fields = [r["field"] for r in data["passed_rules"]]
    assert "income" in passed_fields
    assert "category" in passed_fields
    assert "domicile_state" in passed_fields

    # Check recommendations endpoint
    rec_res = client.get(f"/api/recommendations/{student_id}")
    assert rec_res.status_code == 200
    matched = next(r for r in rec_res.json()["recommendations"] if r["scholarship_id"] == scholarship.id)
    assert matched["match_status"] == "likely_eligible"
    assert len(matched["failed_rules"]) == 0
    assert len(matched["passed_rules"]) > 0


def test_scenario_2_student_failing_income_condition(isolated_client):
    client = isolated_client
    db = next(isolated_client.app.dependency_overrides[get_db]())

    scholarship = Scholarship(
        scholarship_name="Low Income Support Scholarship",
        provider="Govt of Maharashtra",
        state="Maharashtra",
        category="General",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=200000,
        is_active=True,
        active_status="active",
        deadline=datetime(2035, 12, 31, tzinfo=timezone.utc),
    )
    db.add(scholarship)
    db.commit()

    student_payload = {
        "full_name": "Karan Kapoor",
        "email": "karan@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "Tech Institute",
        "academic_score": 80,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Male",
        "annual_family_income": 600000,  # Exceeds max_income
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    create_res = client.post("/api/profile/submit-and-recommend", json=student_payload)
    student_id = create_res.json()["student"]["id"]

    res = client.get(f"/api/scholarships/{scholarship.id}/eligibility/{student_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "not_matched"

    income_failure = next(r for r in data["failed_rules"] if r["field"] == "income")
    assert income_failure["status"] == "failed"
    assert "exceeds" in income_failure["message"].lower()


def test_scenario_3_student_failing_category_condition(isolated_client):
    client = isolated_client
    db = next(isolated_client.app.dependency_overrides[get_db]())

    scholarship = Scholarship(
        scholarship_name="Post-Matric Scholarship for SC Students",
        provider="Govt of Maharashtra",
        state="Maharashtra",
        category="SC",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=500000,
        is_active=True,
        active_status="active",
        deadline=datetime(2035, 12, 31, tzinfo=timezone.utc),
    )
    db.add(scholarship)
    db.commit()

    student_payload = {
        "full_name": "Pooja Hegde",
        "email": "pooja@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "Tech Institute",
        "academic_score": 85,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",  # General does not match SC
        "gender": "Female",
        "annual_family_income": 200000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    create_res = client.post("/api/profile/submit-and-recommend", json=student_payload)
    student_id = create_res.json()["student"]["id"]

    res = client.get(f"/api/scholarships/{scholarship.id}/eligibility/{student_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "not_matched"

    category_failure = next(r for r in data["failed_rules"] if r["field"] == "category")
    assert category_failure["status"] == "failed"
    assert "does not match" in category_failure["message"].lower()


def test_scenario_4_student_with_missing_domicile_state(isolated_client):
    client = isolated_client
    db = next(isolated_client.app.dependency_overrides[get_db]())

    scholarship = Scholarship(
        scholarship_name="State Resident Grant",
        provider="Govt of Maharashtra",
        state="Maharashtra",
        category="General",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=500000,
        is_active=True,
        active_status="active",
        deadline=datetime(2035, 12, 31, tzinfo=timezone.utc),
    )
    db.add(scholarship)
    db.commit()

    student_payload = {
        "full_name": "Ananya Roy",
        "email": "ananya@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "Tech Institute",
        "academic_score": 85,
        "score_type": "percentage",
        "domicile_state": None,  # Missing domicile
        "study_state": None,
        "category": "General",
        "gender": "Female",
        "annual_family_income": 200000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    create_res = client.post("/api/profile/submit-and-recommend", json=student_payload)
    student_id = create_res.json()["student"]["id"]

    res = client.get(f"/api/scholarships/{scholarship.id}/eligibility/{student_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "needs_verification"

    domicile_rule = next(r for r in data["unknown_rules"] if r["field"] == "domicile_state")
    assert domicile_rule["status"] == "unknown"
    assert "missing" in domicile_rule["message"].lower()


def test_scenario_5_student_with_unknown_or_unverified_requirements(isolated_client):
    client = isolated_client
    db = next(isolated_client.app.dependency_overrides[get_db]())

    scholarship = Scholarship(
        scholarship_name="Unverified Status Special Welfare Grant",
        provider="Govt of India",
        state="All India",
        category="General",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=500000,
        is_active=True,
        active_status="unknown",  # Source data does not confirm if applications open
        deadline=datetime(2035, 12, 31, tzinfo=timezone.utc),
    )
    db.add(scholarship)
    db.commit()

    student_payload = {
        "full_name": "Vikram Seth",
        "email": "vikram@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "Tech Institute",
        "academic_score": 85,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Male",
        "annual_family_income": 200000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    create_res = client.post("/api/profile/submit-and-recommend", json=student_payload)
    student_id = create_res.json()["student"]["id"]

    res = client.get(f"/api/scholarships/{scholarship.id}/eligibility/{student_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["match_status"] == "needs_verification"

    active_rule = next(r for r in data["unknown_rules"] if r["field"] == "active")
    assert active_rule["status"] == "unknown"
    assert "verified" in active_rule["message"].lower() or "source data" in active_rule["message"].lower()
