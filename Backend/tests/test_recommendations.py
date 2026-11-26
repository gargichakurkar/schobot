from fastapi.testclient import TestClient

from app.main import app

def test_submit_and_recommend_creates_profile_and_matches(isolated_client):
    client = isolated_client
    payload = {
        "full_name": "Mehul Patil",
        "email": "mehul@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "State Tech Institute",
        "academic_score": 87,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Male",
        "has_disability_certificate": False,
        "annual_family_income": 180000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    submit = client.post("/api/profile/submit-and-recommend", json=payload)
    assert submit.status_code == 200, submit.text
    body = submit.json()

    assert body["student"]["email"] == payload["email"]
    assert body["student"]["id"]
    assert body["student"]["annual_family_income"] == payload["annual_family_income"]
    assert "recommendations" in body
    assert isinstance(body["recommendations"], list)
    for recommendation in body["recommendations"]:
        assert {"state", "scholarship_type", "deadline", "official_link", "doc_status"} <= recommendation.keys()
        assert recommendation["doc_status"] == "not_started"

    student_id = body["student"]["id"]
    recs = client.get(f"/api/recommendations/{student_id}")
    assert recs.status_code == 200
    assert isinstance(recs.json()["recommendations"], list)
    for recommendation in recs.json()["recommendations"]:
        assert {"state", "scholarship_type", "deadline", "official_link", "doc_status"} <= recommendation.keys()

    if recs.json()["recommendations"]:
        scholarship_id = recs.json()["recommendations"][0]["scholarship_id"]
        documents = client.get(
            f"/api/recommendations/{student_id}/scholarship/{scholarship_id}/documents"
        )
        assert documents.status_code == 200
        assert documents.json()["documents"]
        assert all(document["status"] == "not_uploaded" for document in documents.json()["documents"])

        document_name = documents.json()["documents"][0]["document_name"]
        update_document = client.patch(
            f"/api/recommendations/{student_id}/scholarship/{scholarship_id}/documents/{document_name}",
            json={"status": "uploaded", "notes": "Uploaded during test"},
        )
        assert update_document.status_code == 200, update_document.text
        assert update_document.json()["status"] == "uploaded"
        assert update_document.json()["notes"] == "Uploaded during test"

        refreshed_documents = client.get(
            f"/api/recommendations/{student_id}/scholarship/{scholarship_id}/documents"
        )
        persisted_document = next(
            document
            for document in refreshed_documents.json()["documents"]
            if document["document_name"] == document_name
        )
        assert persisted_document["status"] == "uploaded"
        assert persisted_document["notes"] == "Uploaded during test"

        progress = client.patch(
            f"/api/recommendations/{student_id}/scholarship/{scholarship_id}/progress",
            json={"doc_status": "verified"},
        )
        assert progress.status_code == 200, progress.text
        assert progress.json()["doc_status"] == "verified"

        refreshed = client.get(f"/api/recommendations/{student_id}")
        persisted = next(
            recommendation
            for recommendation in refreshed.json()["recommendations"]
            if recommendation["scholarship_id"] == scholarship_id
        )
        assert persisted["doc_status"] == "verified"


def test_profile_update_automatically_refreshes_recommendations(isolated_client):
    client = isolated_client
    from app.core.database import get_db
    from app.models.scholarship import Scholarship

    db = next(app.dependency_overrides[get_db]())
    scholarship = Scholarship(
        scholarship_name="State SC Higher Education Grant",
        provider="Govt of Maharashtra",
        state="Maharashtra",
        category="SC",
        eligible_level="Undergraduate",
        eligible_course="B.Tech",
        max_income=300000,
        is_active=True,
    )
    db.add(scholarship)
    db.commit()
    db.close()

    payload = {
        "full_name": "Rohan Deshmukh",
        "email": "rohan@example.com",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "college_name": "COEP Pune",
        "academic_score": 85,
        "score_type": "percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Male",
        "annual_family_income": 150000,
        "has_income_certificate": True,
        "password": "SecurePassword123!",
        "profile_completed": True,
    }

    submit = client.post("/api/profile/submit-and-recommend", json=payload)
    assert submit.status_code == 200
    student_id = submit.json()["student"]["id"]

    recs_initial = client.get(f"/api/recommendations/{student_id}").json()["recommendations"]
    assert len(recs_initial) == 1
    # Initially category should be General and failed
    cat_rule_initial = next(
        r for r in recs_initial[0]["failed_rules"] if r["field"] == "category"
    )
    assert cat_rule_initial["student_value"] == "general"

    # Update profile with SC category and 950000 income
    auth_token = submit.json().get("access_token") or submit.json()["student"].get("access_token")
    assert auth_token, "Registration response must contain an access token"

    update_res = client.put(
        f"/api/profiles/{student_id}",
        json={"category": "SC", "annual_family_income": 950000},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["category"] == "SC"
    assert update_res.json()["annual_family_income"] == 950000

    # Verify recommendations are immediately updated without stale data
    recs_updated = client.get(f"/api/recommendations/{student_id}").json()["recommendations"]
    assert len(recs_updated) == 1

    # Now category rule passed for SC!
    cat_rule_updated = next(
        r for r in recs_updated[0]["passed_rules"] if r["field"] == "category"
    )
    assert cat_rule_updated["student_value"] == "sc"

    # And income rule reflects new income 950000
    income_rule_updated = next(
        r for r in recs_updated[0]["failed_rules"] if r["field"] == "income"
    )
    assert income_rule_updated["student_value"] == 950000.0
