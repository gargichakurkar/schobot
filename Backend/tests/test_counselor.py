from __future__ import annotations

from uuid import uuid4

import pytest
from app.core.database import get_db
from app.models.counselor_link import CounselorLink
from auth import create_access_token


def create_test_student_with_token(client, name="Test Student") -> tuple[str, str, dict[str, str]]:
    res = client.post(
        "/api/profiles",
        json={
            "full_name": name,
            "email": f"{uuid4().hex[:8]}@example.com",
            "password": "SecurePassword123!",
            "education_level": "Undergraduate",
            "course": "Computer Engineering",
            "study_year": "2",
            "domicile_state": "Maharashtra",
            "category": "OBC",
            "annual_family_income": 200000,
            "profile_completed": True,
        },
    )
    assert res.status_code == 200
    student_id = res.json()["id"]
    token = create_access_token({"sub": student_id, "role": "student"})
    headers = {"Authorization": f"Bearer {token}"}
    return student_id, token, headers


def test_create_counselor_link_unauthenticated_rejected(isolated_client):
    """Unauthenticated requests to /api/counselor/link must be rejected with HTTP 401."""
    res = isolated_client.post(
        "/api/counselor/link",
        json={
            "counselor_email": "counselor@example.com",
            "language": "en",
        },
    )
    assert res.status_code == 401
    assert "detail" in res.json()


def test_student_cannot_create_link_for_another_student(isolated_client):
    """Student A cannot create a counselor link for Student B by supplying Student B's ID."""
    student_a_id, _, headers_a = create_test_student_with_token(isolated_client, "Student A")
    student_b_id, _, _ = create_test_student_with_token(isolated_client, "Student B")

    # Student A attempts to create a link for Student B
    res = isolated_client.post(
        "/api/counselor/link",
        json={
            "student_id": student_b_id,
            "counselor_email": "attacker_counselor@example.com",
            "language": "en",
        },
        headers=headers_a,
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # Verify no link was created for Student B
    db = next(isolated_client.app.dependency_overrides[get_db]())
    b_link = db.query(CounselorLink).filter(CounselorLink.student_id == student_b_id).first()
    assert b_link is None


def test_student_cannot_replace_link_for_another_student(isolated_client):
    """Student A cannot replace or tamper with Student B's existing counselor link."""
    student_a_id, _, headers_a = create_test_student_with_token(isolated_client, "Student A")
    student_b_id, _, headers_b = create_test_student_with_token(isolated_client, "Student B")

    # Student B creates legitimate counselor link
    b_create = isolated_client.post(
        "/api/counselor/link",
        json={
            "counselor_email": "legit_counselor@school.org",
            "language": "en",
        },
        headers=headers_b,
    )
    assert b_create.status_code == 200
    original_b_token = b_create.json()["token"]

    # Student A attempts to overwrite Student B's counselor link
    res = isolated_client.post(
        "/api/counselor/link",
        json={
            "student_id": student_b_id,
            "counselor_email": "malicious_counselor@evil.org",
            "language": "mr",
        },
        headers=headers_a,
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # Verify Student B's link remains intact with original token and email
    db = next(isolated_client.app.dependency_overrides[get_db]())
    b_link = db.query(CounselorLink).filter(CounselorLink.student_id == student_b_id).first()
    assert b_link is not None
    assert b_link.token == original_b_token
    assert b_link.counselor_email == "legit_counselor@school.org"
    assert b_link.language == "en"


def test_authenticated_student_creates_and_replaces_own_link(isolated_client):
    """Authenticated student can create and replace their counselor link, deriving ID from token."""
    student_id, _, headers = create_test_student_with_token(isolated_client, "Student A")

    # 1. Create link (omitting student_id from request body)
    res = isolated_client.post(
        "/api/counselor/link",
        json={
            "counselor_email": "advisor1@college.edu",
            "language": "en",
        },
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["language"] == "en"
    assert data["delivery_status"] == "not_configured"
    first_token = data["token"]
    assert len(first_token) >= 32

    # Verify in DB that the link belongs to student_id
    db = next(isolated_client.app.dependency_overrides[get_db]())
    link = db.query(CounselorLink).filter(CounselorLink.student_id == student_id).first()
    assert link is not None
    assert link.token == first_token
    assert link.counselor_email == "advisor1@college.edu"

    # 2. Replace link with updated email and language
    res2 = isolated_client.post(
        "/api/counselor/link",
        json={
            "counselor_email": "advisor2@college.edu",
            "language": "mr",
        },
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["language"] == "mr"
    second_token = data2["token"]
    assert second_token != first_token

    # Verify updated in DB
    db.expire_all()
    updated_link = db.query(CounselorLink).filter(CounselorLink.student_id == student_id).first()
    assert updated_link.token == second_token
    assert updated_link.counselor_email == "advisor2@college.edu"
    assert updated_link.language == "mr"


def test_authenticated_student_matching_student_id_allowed(isolated_client):
    """Authenticated student providing their own matching student_id succeeds."""
    student_id, _, headers = create_test_student_with_token(isolated_client, "Student A")

    res = isolated_client.post(
        "/api/counselor/link",
        json={
            "student_id": student_id,
            "counselor_email": "counselor@school.edu",
            "language": "en",
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["token"]


def test_counselor_link_revocation(isolated_client):
    """Authenticated student can revoke counselor link, blocking further access."""
    student_id, _, headers = create_test_student_with_token(isolated_client, "Student Revoker")

    # 1. Create link
    create_res = isolated_client.post(
        "/api/counselor/link",
        json={"counselor_email": "counselor@school.edu", "language": "en"},
        headers=headers,
    )
    assert create_res.status_code == 200
    token = create_res.json()["token"]

    # 2. View link works initially
    view_res = isolated_client.get(f"/api/counselor/view/{token}")
    assert view_res.status_code == 200

    # 3. Revoke link
    revoke_res = isolated_client.delete("/api/counselor/link", headers=headers)
    assert revoke_res.status_code == 200
    assert revoke_res.json()["status"] == "success"

    # 4. Accessing view now returns 403
    revoked_view = isolated_client.get(f"/api/counselor/view/{token}")
    assert revoked_view.status_code == 403
    assert "revoked" in revoked_view.json()["detail"].lower()


def test_counselor_link_expiration(isolated_client):
    """Expired counselor link cannot be accessed."""
    from datetime import datetime, timedelta, timezone
    student_id, _, headers = create_test_student_with_token(isolated_client, "Student Expire")

    # Create link
    create_res = isolated_client.post(
        "/api/counselor/link",
        json={"counselor_email": "counselor@school.edu", "language": "en"},
        headers=headers,
    )
    assert create_res.status_code == 200
    token = create_res.json()["token"]

    # Set expiry in the past
    db = next(isolated_client.app.dependency_overrides[get_db]())
    link = db.query(CounselorLink).filter(CounselorLink.token == token).first()
    link.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()

    # Accessing view returns 403
    view_res = isolated_client.get(f"/api/counselor/view/{token}")
    assert view_res.status_code == 403
    assert "expired" in view_res.json()["detail"].lower()
