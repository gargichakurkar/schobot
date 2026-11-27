from fastapi.testclient import TestClient

from app.main import app


def test_create_and_get_profile(isolated_client):
    client = isolated_client
    payload = {
        "full_name": "Riya Shah",
        "email": "riya@example.com",
        "password": "SecurePassword123!",
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
    auth_headers = {"Authorization": f"Bearer {data['access_token']}"}

    get_response = client.get(f"/api/profiles/{student_id}", headers=auth_headers)
    assert get_response.status_code == 200
    assert get_response.json()["email"] == payload["email"]

    update_response = client.put(
        f"/api/profiles/{student_id}",
        json={"academic_score": 90},
        headers=auth_headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["academic_score"] == 90


def test_registration_without_password_rejected(isolated_client):
    """Registration without a password must be rejected with HTTP 422."""
    payload = {
        "full_name": "No Password Student",
        "email": "nopass@example.com",
        "profile_completed": True,
    }
    response = isolated_client.post("/api/profiles", json=payload)
    assert response.status_code == 422


def test_registration_with_short_password_rejected(isolated_client):
    """Passwords shorter than 10 characters must be rejected with HTTP 422."""
    payload = {
        "full_name": "Short Password Student",
        "email": "shortpass@example.com",
        "password": "short",
        "profile_completed": True,
    }
    response = isolated_client.post("/api/profiles", json=payload)
    assert response.status_code == 422


def test_registration_duplicate_email_rejected(isolated_client):
    """Registering with an already registered email must be rejected with HTTP 409."""
    payload = {
        "full_name": "Student First",
        "email": "duplicate.test@example.com",
        "password": "ValidPassword123!",
        "profile_completed": True,
    }
    res1 = isolated_client.post("/api/profiles", json=payload)
    assert res1.status_code == 200

    # Attempt to register again with same email
    payload2 = {
        "full_name": "Student Second",
        "email": "DUPLICATE.TEST@example.com",
        "password": "AnotherPassword123!",
        "profile_completed": True,
    }
    res2 = isolated_client.post("/api/profiles", json=payload2)
    assert res2.status_code == 409
    assert "already exists" in res2.json()["detail"].lower()


def test_profile_creation_returns_jwt_access_token(isolated_client):
    """Creating a profile returns access_token for immediate authentication."""
    client = isolated_client
    payload = {
        "full_name": "Aarav Patel",
        "email": "aarav@example.com",
        "password": "AaravPassword123!",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2",
        "domicile_state": "Maharashtra",
        "category": "General",
        "annual_family_income": 400000,
        "profile_completed": True,
    }
    response = client.post("/api/profiles", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"]
    assert data["id"]


def test_student_token_login_flows(isolated_client):
    """Students can obtain access tokens by student_id, email, or general identifier with password."""
    client = isolated_client
    payload = {
        "full_name": "Pooja Deshmukh",
        "email": "pooja.d@example.com",
        "password": "SecurePassword123!",
        "education_level": "Postgraduate",
        "course": "M.Sc",
        "study_year": "1",
        "domicile_state": "Maharashtra",
        "category": "OBC",
        "annual_family_income": 180000,
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["id"]

    # 1. Login with student_id and password
    res1 = client.post("/api/auth/token", json={"student_id": student_id, "password": "SecurePassword123!"})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["access_token"]
    assert data1["student_id"] == student_id
    assert data1["student"]["full_name"] == "Pooja Deshmukh"

    # 2. Login with email (case-insensitive) and password
    res2 = client.post("/api/auth/token", json={"email": "POOJA.D@EXAMPLE.COM", "password": "SecurePassword123!"})
    assert res2.status_code == 200
    assert res2.json()["student_id"] == student_id

    # 3. Login with general identifier (email) and password
    res3 = client.post("/api/auth/token", json={"identifier": "pooja.d@example.com", "password": "SecurePassword123!"})
    assert res3.status_code == 200
    assert res3.json()["student_id"] == student_id

    # 4. Login with general identifier (student_id) and password
    res4 = client.post("/api/auth/token", json={"identifier": student_id, "password": "SecurePassword123!"})
    assert res4.status_code == 200
    assert res4.json()["student_id"] == student_id

    # 5. Wrong password returns 401
    res_wrong = client.post("/api/auth/token", json={"identifier": student_id, "password": "WrongPassword"})
    assert res_wrong.status_code == 401
    assert "invalid credentials" in res_wrong.json()["detail"].lower()

    # 6. Missing password returns 422
    res_nopass = client.post("/api/auth/token", json={"identifier": student_id})
    assert res_nopass.status_code == 422

    # 7. Non-existent identifier returns 401
    res5 = client.post("/api/auth/token", json={"identifier": "nonexistent@example.com", "password": "any"})
    assert res5.status_code == 401

    # 8. Missing identifier returns 422
    res6 = client.post("/api/auth/token", json={"password": "any"})
    assert res6.status_code == 422


def test_login_account_without_password_requires_activation(isolated_client):
    """Accounts created without password receive 403 instructing OTP activation."""
    client = isolated_client
    # Simulate legacy account directly in DB without password_hash
    from app.core.database import get_db
    from app.models.student_profile import StudentProfile
    db = next(client.app.dependency_overrides[get_db]())
    legacy = StudentProfile(
        full_name="Legacy Student",
        email="legacy@example.com",
        password_hash=None,
        profile_completed=True,
    )
    db.add(legacy)
    db.commit()
    db.refresh(legacy)

    res = client.post("/api/auth/token", json={"identifier": legacy.id, "password": "AnyPassword123!"})
    assert res.status_code == 403
    assert "activation required" in res.json()["detail"].lower()


def test_otp_request_and_activation_flow(isolated_client, monkeypatch):
    """Test full OTP activation: request OTP -> verify and set password -> sign in."""
    from app.services.email_service import get_email_service
    email_service = get_email_service()
    monkeypatch.setattr(email_service, "send_otp_email", lambda to, otp: True)

    client = isolated_client
    payload = {
        "full_name": "OTP Student",
        "email": "otp.student@example.com",
        "password": "InitialPassword123!",
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["id"]

    # Request OTP
    req_res = client.post("/api/auth/request-otp", json={"identifier": student_id})
    assert req_res.status_code == 200
    data = req_res.json()
    assert data["status"] == "success"
    assert "masked_email" in data

    # Read the OTP from database in test fixture
    from app.core.database import get_db
    from app.models.student_profile import StudentProfile
    db = next(client.app.dependency_overrides[get_db]())
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    assert student.otp_hash is not None
    assert student.otp_expires_at is not None

    # Test invalid OTP
    bad_res = client.post(
        "/api/auth/verify-otp-set-password",
        json={"identifier": student_id, "otp": "999999", "new_password": "NewSecurePassword123!"},
    )
    assert bad_res.status_code == 400
    assert "invalid" in bad_res.json()["detail"].lower()

    # Set known OTP
    from auth import hash_password
    known_otp = "123456"
    student.otp_hash = hash_password(known_otp)
    student.otp_attempts = 0
    db.commit()

    # Verify and set password
    ok_res = client.post(
        "/api/auth/verify-otp-set-password",
        json={"identifier": student_id, "otp": known_otp, "new_password": "NewSecurePassword123!"},
    )
    assert ok_res.status_code == 200
    ok_data = ok_res.json()
    assert ok_data["access_token"]
    assert ok_data["student_id"] == student_id

    # Verify student can now log in with new password
    login_res = client.post(
        "/api/auth/token",
        json={"identifier": student_id, "password": "NewSecurePassword123!"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["access_token"]


def test_otp_request_fails_safely_when_email_unconfigured(isolated_client, monkeypatch):
    """When Resend is not configured, requesting OTP returns 503 and does not claim email sent."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "resend_api_key", "")

    client = isolated_client
    payload = {
        "full_name": "Unconfigured Email Student",
        "email": "unconf@example.com",
        "password": "Password12345!",
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["id"]

    res = client.post("/api/auth/request-otp", json={"identifier": student_id})
    assert res.status_code == 503
    assert "not configured" in res.json()["detail"].lower()
    assert "resend" in res.json()["detail"].lower()


def test_resend_send_otp_email_success_with_mocked_http(monkeypatch):
    """Verify Resend HTTPS API sends payload to https://api.resend.com/emails with Bearer auth."""
    import httpx
    from app.core.config import settings
    from app.services.email_service import get_email_service

    monkeypatch.setattr(settings, "resend_api_key", "re_test_mock_secret_key_123")
    monkeypatch.setattr(settings, "resend_from_email", "Schobot <verify@schobot.com>")

    captured_requests = []

    def mock_post(self, url, json=None, headers=None, **kwargs):
        captured_requests.append({"url": url, "json": json, "headers": headers})
        # Mock successful Resend response
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"id": "re_msg_mock_id_999"}, request=request)

    monkeypatch.setattr(httpx.Client, "post", mock_post)

    email_service = get_email_service()
    assert email_service.is_configured is True
    result = email_service.send_otp_email("student@example.com", "849201")
    assert result is True

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://api.resend.com/emails"
    assert req["headers"]["Authorization"] == "Bearer re_test_mock_secret_key_123"
    assert req["headers"]["Content-Type"] == "application/json"
    assert req["json"]["to"] == ["student@example.com"]
    assert req["json"]["from"] == "Schobot <verify@schobot.com>"
    assert "849201" in req["json"]["subject"]
    assert "849201" in req["json"]["text"]
    assert "849201" in req["json"]["html"]


def test_resend_send_otp_email_http_error_handled_cleanly(monkeypatch):
    """Verify Resend HTTP 422/401 errors raise RuntimeError without leaking sensitive keys."""
    import httpx
    import pytest
    from app.core.config import settings
    from app.services.email_service import get_email_service

    monkeypatch.setattr(settings, "resend_api_key", "re_test_mock_secret_key_123")

    def mock_post_fail(self, url, json=None, headers=None, **kwargs):
        request = httpx.Request("POST", url)
        return httpx.Response(422, json={"message": "Domain not verified"}, request=request)

    monkeypatch.setattr(httpx.Client, "post", mock_post_fail)

    email_service = get_email_service()
    with pytest.raises(RuntimeError) as exc_info:
        email_service.send_otp_email("student@example.com", "849201")

    assert "HTTP 422" in str(exc_info.value)
    # Ensure api key was never placed in exception message
    assert "re_test_mock_secret_key_123" not in str(exc_info.value)


def test_otp_request_unknown_account_returns_generic_response(isolated_client, monkeypatch):
    """Requesting OTP for non-existent account returns generic success without attempting email delivery."""
    from app.services.email_service import get_email_service
    email_service = get_email_service()
    email_sent = []
    monkeypatch.setattr(email_service, "send_otp_email", lambda to, otp: email_sent.append((to, otp)))

    res = isolated_client.post("/api/auth/request-otp", json={"identifier": "unknown.user@example.com"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "if an account exists" in data["message"].lower()
    assert len(email_sent) == 0  # No email sent for unknown user


def test_otp_request_email_failure_returns_generic_error(isolated_client, monkeypatch):
    """When email delivery raises an internal exception, return generic 500 without exposing raw exception details."""
    from app.services.email_service import get_email_service
    email_service = get_email_service()

    def mock_send_fail(to, otp):
        raise RuntimeError("CRITICAL_INTERNAL_RESEND_API_OR_SOCKET_ERROR")

    monkeypatch.setattr(email_service, "send_otp_email", mock_send_fail)

    client = isolated_client
    payload = {
        "full_name": "Email Fail Student",
        "email": "emailfail@example.com",
        "password": "Password12345!",
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    student_id = create_res.json()["id"]

    res = client.post("/api/auth/request-otp", json={"identifier": student_id})
    assert res.status_code == 500
    assert "CRITICAL_INTERNAL_RESEND" not in res.json()["detail"]
    assert "failed to deliver verification email" in res.json()["detail"].lower()


def test_student_profile_response_does_not_expose_auth_secrets(isolated_client):
    """Ensure student profile API responses never contain password_hash, otp_hash, or otp_expires_at."""
    client = isolated_client
    payload = {
        "full_name": "Secret Test Student",
        "email": "secret@example.com",
        "password": "SuperSecretPassword123!",
        "profile_completed": True,
    }
    res = client.post("/api/profiles", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "password_hash" not in data
    assert "otp_hash" not in data
    assert "otp_expires_at" not in data
    assert "otp_attempts" not in data

    student_id = data["id"]
    auth_headers = {"Authorization": f"Bearer {data['access_token']}"}
    get_res = client.get(f"/api/profiles/{student_id}", headers=auth_headers)
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert "password_hash" not in get_data
    assert "otp_hash" not in get_data
    assert "otp_expires_at" not in get_data
    assert "otp_attempts" not in get_data


def test_otp_max_attempts_lockout(isolated_client):
    """After 5 failed OTP attempts, verification is locked out with HTTP 429."""
    from app.core.database import get_db
    from app.models.student_profile import StudentProfile
    from auth import hash_password

    client = isolated_client
    payload = {
        "full_name": "Lockout Student",
        "email": "lockout@example.com",
        "password": "Password12345!",
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["id"]

    db = next(client.app.dependency_overrides[get_db]())
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    student.otp_hash = hash_password("111111")
    from datetime import datetime, timedelta, timezone
    student.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    student.otp_attempts = 5
    db.commit()

    res = client.post(
        "/api/auth/verify-otp-set-password",
        json={"identifier": student_id, "otp": "111111", "new_password": "NewPassword12345!"},
    )
    assert res.status_code == 429
    assert "too many" in res.json()["detail"].lower()


def test_otp_expired_rejected(isolated_client):
    """Expired OTP verification attempts are rejected with HTTP 400."""
    from app.core.database import get_db
    from app.models.student_profile import StudentProfile
    from auth import hash_password
    from datetime import datetime, timedelta, timezone

    client = isolated_client
    payload = {
        "full_name": "Expired OTP Student",
        "email": "expired@example.com",
        "password": "Password12345!",
        "profile_completed": True,
    }
    create_res = client.post("/api/profiles", json=payload)
    assert create_res.status_code == 200
    student_id = create_res.json()["id"]

    db = next(client.app.dependency_overrides[get_db]())
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    student.otp_hash = hash_password("222222")
    student.otp_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)  # expired
    student.otp_attempts = 0
    db.commit()

    res = client.post(
        "/api/auth/verify-otp-set-password",
        json={"identifier": student_id, "otp": "222222", "new_password": "NewPassword12345!"},
    )
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


def test_complete_register_login_vault_flow(isolated_client, tmp_path, monkeypatch):
    """Complete flow: register -> login -> use token for vault upload -> list vault."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    client = isolated_client

    # 1. Register student with password
    reg_res = client.post(
        "/api/profiles",
        json={
            "full_name": "Sneha Kadam",
            "email": "sneha.k@example.com",
            "password": "MyVaultPassword123!",
            "education_level": "Undergraduate",
            "course": "Civil Engineering",
            "study_year": "3",
            "domicile_state": "Maharashtra",
            "category": "EWS",
            "annual_family_income": 250000,
            "profile_completed": True,
        },
    )
    assert reg_res.status_code == 200
    student_id = reg_res.json()["id"]

    # 2. Login with registered email and password
    login_res = client.post(
        "/api/auth/token",
        json={"identifier": "sneha.k@example.com", "password": "MyVaultPassword123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {token}"}

    # 3. Access Document Vault without token is rejected
    vault_unauth = client.get(f"/api/student/documents?student_id={student_id}")
    assert vault_unauth.status_code == 401

    # 4. Upload document to vault with Bearer token
    files = {"file": ("income_cert.pdf", b"%PDF-1.4\nvalid pdf\n%%EOF", "application/pdf")}
    upload_res = client.post(
        "/api/student/documents/upload",
        data={"student_id": student_id, "document_type": "Income Certificate", "run_ocr": "false"},
        files=files,
        headers=auth_headers,
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # 5. Retrieve documents from vault with Bearer token
    vault_res = client.get(f"/api/student/documents?student_id={student_id}", headers=auth_headers)
    assert vault_res.status_code == 200
    docs = vault_res.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["id"] == doc_id

def test_profile_routes_require_authentication(isolated_client):
    client = isolated_client
    payload = {
        "full_name": "Unauthenticated Student",
        "email": "unauth.profile@example.com",
        "password": "SecurePassword123!",
        "profile_completed": True,
    }
    created = client.post("/api/profiles", json=payload)
    assert created.status_code == 200
    student_id = created.json()["id"]

    get_response = client.get(f"/api/profiles/{student_id}")
    assert get_response.status_code == 401

    update_response = client.put(
        f"/api/profiles/{student_id}",
        json={"academic_score": 90},
    )
    assert update_response.status_code == 401


def test_student_cannot_access_or_update_another_profile(isolated_client):
    client = isolated_client

    student_a = client.post("/api/profiles", json={
        "full_name": "Student A",
        "email": "student.a.security@example.com",
        "password": "SecurePassword123!",
        "profile_completed": True,
    })
    student_b = client.post("/api/profiles", json={
        "full_name": "Student B",
        "email": "student.b.security@example.com",
        "password": "SecurePassword123!",
        "profile_completed": True,
    })

    assert student_a.status_code == 200, student_a.text
    assert student_b.status_code == 200, student_b.text

    data_a = student_a.json()
    data_b = student_b.json()
    headers_a = {"Authorization": f"Bearer {data_a['access_token']}"}
    headers_b = {"Authorization": f"Bearer {data_b['access_token']}"}

    own_profile = client.get(
        f"/api/profiles/{data_a['id']}",
        headers=headers_a,
    )
    assert own_profile.status_code == 200

    other_profile = client.get(
        f"/api/profiles/{data_b['id']}",
        headers=headers_a,
    )
    assert other_profile.status_code == 403

    other_update = client.put(
        f"/api/profiles/{data_b['id']}",
        json={"academic_score": 95},
        headers=headers_a,
    )
    assert other_update.status_code == 403

    student_b_own_profile = client.get(
        f"/api/profiles/{data_b['id']}",
        headers=headers_b,
    )
    assert student_b_own_profile.status_code == 200
