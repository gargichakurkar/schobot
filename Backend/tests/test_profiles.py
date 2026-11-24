from fastapi.testclient import TestClient

from app.main import app


def test_create_and_get_profile(isolated_client):
    client = isolated_client
    payload = {
        "full_name": "Riya Shah",
        "email": "riya@example.com",
        "education_level": "Undergraduate",
        "course": "B.Sc",
        "study_year": "1",
        "college_name": "XYZ College",
        "academic_score": 88,
        "score_type": "percentage",
        "domicile_state": "Gujarat",
        "study_state": "Gujarat",
        "category": "OBC",
        "gender": "Female",
        "has_disability_certificate": False,
        "annual_family_income": 220000,
        "has_income_certificate": True,
        "profile_completed": True,
    }

    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 200, response.text
    data = response.json()

    student_id = data["id"]
    assert data["full_name"] == payload["full_name"]

    get_response = client.get(f"/api/profiles/{student_id}")
    assert get_response.status_code == 200
    assert get_response.json()["email"] == payload["email"]

    update_response = client.put(f"/api/profiles/{student_id}", json={"academic_score": 90})
    assert update_response.status_code == 200
    assert update_response.json()["academic_score"] == 90
