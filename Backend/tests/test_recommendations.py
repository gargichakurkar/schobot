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
