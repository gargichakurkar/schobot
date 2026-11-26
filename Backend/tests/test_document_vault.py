from __future__ import annotations

import io
from uuid import uuid4

import pytest
from app.core.config import settings
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.services.storage_service import StorageError, StorageService
from auth import create_access_token

TEST_SECRET_KEY = "test-only-signing-key-with-adequate-length-32-chars"


def make_dummy_pdf() -> bytes:
    return b"%PDF-1.4\n%dummy pdf content for testing\n%%EOF"


def make_dummy_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRdummy"


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


def make_counselor_headers() -> dict[str, str]:
    token = create_access_token({"sub": "counselor-1", "role": "counselor"})
    return {"Authorization": f"Bearer {token}"}


def test_vault_upload_valid_pdf_and_list(isolated_client, tmp_path, monkeypatch):
    """Uploading a valid PDF saves to vault, sets status to pending_review, and can be retrieved."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    student_id, token, headers = create_test_student_with_token(isolated_client)

    pdf_bytes = make_dummy_pdf()
    files = {"file": ("income_2026.pdf", pdf_bytes, "application/pdf")}
    data = {
        "student_id": student_id,
        "document_type": "Income Certificate",
        "run_ocr": "false",
    }

    res = isolated_client.post("/api/student/documents/upload", data=data, files=files, headers=headers)
    assert res.status_code == 200
    doc = res.json()
    assert doc["student_id"] == student_id
    assert doc["document_type"] == "Income Certificate"
    assert doc["original_filename"] == "income_2026.pdf"
    assert doc["verification_status"] == "pending_review"  # Not auto-verified
    assert doc["download_url"]

    # List documents for student
    list_res = isolated_client.get(f"/api/student/documents?student_id={student_id}", headers=headers)
    assert list_res.status_code == 200
    docs = list_res.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["id"] == doc["id"]


def test_vault_upload_valid_image(isolated_client, tmp_path, monkeypatch):
    """Uploading a PNG image succeeds and stores correct metadata."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    student_id, token, headers = create_test_student_with_token(isolated_client)

    png_bytes = make_dummy_png()
    files = {"file": ("aadhaar_front.png", png_bytes, "image/png")}
    data = {
        "student_id": student_id,
        "document_type": "Aadhaar / Identity Proof",
        "run_ocr": "false",
    }

    res = isolated_client.post("/api/student/documents/upload", data=data, files=files, headers=headers)
    assert res.status_code == 200
    assert res.json()["document_type"] == "Aadhaar / Identity Proof"


def test_vault_upload_invalid_file_type_rejected(isolated_client):
    """Unsupported file extension rejected with 415."""
    student_id, token, headers = create_test_student_with_token(isolated_client)
    files = {"file": ("malicious.exe", b"MZdummy", "application/octet-stream")}
    data = {"student_id": student_id, "document_type": "Income Certificate"}

    res = isolated_client.post("/api/student/documents/upload", data=data, files=files, headers=headers)
    assert res.status_code == 415
    assert "Only PDF, JPG, and PNG" in res.json()["detail"]


def test_vault_upload_corrupt_signature_rejected(isolated_client):
    """File pretending to be PDF without magic bytes rejected with 422."""
    student_id, token, headers = create_test_student_with_token(isolated_client)
    files = {"file": ("fake.pdf", b"NOT_A_PDF", "application/pdf")}
    data = {"student_id": student_id, "document_type": "Income Certificate"}

    res = isolated_client.post("/api/student/documents/upload", data=data, files=files, headers=headers)
    assert res.status_code == 422
    assert "supported file format" in res.json()["detail"]


def test_vault_upload_oversized_file_rejected(isolated_client):
    """Files over 10 MB rejected with 413."""
    student_id, token, headers = create_test_student_with_token(isolated_client)
    large_pdf = b"%PDF-" + b"0" * (10 * 1024 * 1024 + 10)
    files = {"file": ("large.pdf", large_pdf, "application/pdf")}
    data = {"student_id": student_id, "document_type": "Income Certificate"}

    res = isolated_client.post("/api/student/documents/upload", data=data, files=files, headers=headers)
    assert res.status_code == 413
    assert "10 MB" in res.json()["detail"]


def test_unauthenticated_requests_rejected(isolated_client):
    """Document endpoints reject unauthenticated requests with HTTP 401."""
    # List documents without token
    res = isolated_client.get("/api/student/documents")
    assert res.status_code == 401

    # Upload without token
    files = {"file": ("doc.pdf", make_dummy_pdf(), "application/pdf")}
    res = isolated_client.post("/api/student/documents/upload", data={"document_type": "Income Certificate"}, files=files)
    assert res.status_code == 401

    # Get single document without token
    res = isolated_client.get("/api/student/documents/some-doc-id")
    assert res.status_code == 401

    # Download document without token
    res = isolated_client.get("/api/student/documents/some-doc-id/download")
    assert res.status_code == 401

    # Delete document without token
    res = isolated_client.delete("/api/student/documents/some-doc-id")
    assert res.status_code == 401


def test_vault_access_control_student_isolation(isolated_client, tmp_path, monkeypatch):
    """Student A cannot list, upload to, view, download, or delete Student B's documents."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    student_a, token_a, headers_a = create_test_student_with_token(isolated_client, "Student A")
    student_b, token_b, headers_b = create_test_student_with_token(isolated_client, "Student B")

    # Student A uploads document
    files = {"file": ("doc_a.pdf", make_dummy_pdf(), "application/pdf")}
    upload_res = isolated_client.post(
        "/api/student/documents/upload",
        data={"student_id": student_a, "document_type": "Income Certificate", "run_ocr": "false"},
        files=files,
        headers=headers_a,
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # 1. Student B attempts to list Student A's documents by changing student_id in query
    res = isolated_client.get(f"/api/student/documents?student_id={student_a}", headers=headers_b)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 2. Student B attempts to upload into Student A's vault
    b_files = {"file": ("injected.pdf", make_dummy_pdf(), "application/pdf")}
    res = isolated_client.post(
        "/api/student/documents/upload",
        data={"student_id": student_a, "document_type": "Income Certificate", "run_ocr": "false"},
        files=b_files,
        headers=headers_b,
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 3. Student B attempts to view Student A's document metadata (referencing doc_id)
    res = isolated_client.get(f"/api/student/documents/{doc_id}", headers=headers_b)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 4. Student B attempts to view Student A's document passing student_id=student_a
    res = isolated_client.get(f"/api/student/documents/{doc_id}?student_id={student_a}", headers=headers_b)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 5. Student B attempts to download Student A's document
    res = isolated_client.get(f"/api/student/documents/{doc_id}/download", headers=headers_b)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 6. Student B attempts to delete Student A's document
    res = isolated_client.delete(f"/api/student/documents/{doc_id}", headers=headers_b)
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]

    # 7. Student A can access and delete their own document
    del_ok = isolated_client.delete(f"/api/student/documents/{doc_id}", headers=headers_a)
    assert del_ok.status_code == 200
    assert del_ok.json()["deleted"] is True


def test_cross_scholarship_document_matching_and_reuse(isolated_client, tmp_path, monkeypatch):
    """A document uploaded once to vault is reused across multiple scholarships requiring it."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    student_id, token, headers = create_test_student_with_token(isolated_client)

    from app.core.database import get_db

    db = next(isolated_client.app.dependency_overrides[get_db]())
    s1 = Scholarship(
        scholarship_name="State Post-Matric OBC Scholarship",
        required_documents="Income Certificate, Caste Certificate, Domicile Certificate",
        category="OBC",
        state="Maharashtra",
    )
    s2 = Scholarship(
        scholarship_name="AICTE Pragati Technical Scheme",
        required_documents="Income Certificate, AICTE admission letter",
        category="General",
        state="All India",
    )
    db.add_all([s1, s2])
    db.commit()
    db.refresh(s1)
    db.refresh(s2)

    # 1. Before upload: verify both scholarships show missing documents
    r1_before = isolated_client.get(f"/api/recommendations/{student_id}/scholarship/{s1.id}/documents")
    assert r1_before.status_code == 200
    data_1_before = r1_before.json()
    assert data_1_before["required_count"] == 3
    assert data_1_before["available_count"] == 0
    assert data_1_before["missing_count"] == 3
    assert all(doc["status"] == "missing" for doc in data_1_before["documents"])

    # 2. Student uploads Income Certificate ONCE into their vault
    files = {"file": ("tahsildar_income_2026.pdf", make_dummy_pdf(), "application/pdf")}
    upload_res = isolated_client.post(
        "/api/student/documents/upload",
        data={"student_id": student_id, "document_type": "Income Certificate", "run_ocr": "false"},
        files=files,
        headers=headers,
    )
    assert upload_res.status_code == 200
    doc_id = upload_res.json()["id"]

    # 3. Check Scholarship 1: Income Certificate is automatically matched and reused!
    r1_after = isolated_client.get(f"/api/recommendations/{student_id}/scholarship/{s1.id}/documents")
    assert r1_after.status_code == 200
    data_1_after = r1_after.json()
    assert data_1_after["required_count"] == 3
    assert data_1_after["available_count"] == 1
    assert data_1_after["missing_count"] == 2

    income_item_1 = next(d for d in data_1_after["documents"] if d["standard_type"] == "Income Certificate")
    assert income_item_1["status"] == "pending_review"  # available in vault
    assert income_item_1["matched_document_id"] == doc_id
    assert income_item_1["matched_document_filename"] == "tahsildar_income_2026.pdf"

    # Caste & Domicile remain missing
    missing_items = [d for d in data_1_after["documents"] if d["status"] == "missing"]
    assert len(missing_items) == 2

    # 4. Check Scholarship 2: The exact same Income Certificate is automatically reused!
    r2_after = isolated_client.get(f"/api/recommendations/{student_id}/scholarship/{s2.id}/documents")
    assert r2_after.status_code == 200
    data_2_after = r2_after.json()
    assert data_2_after["required_count"] == 2
    assert data_2_after["available_count"] == 1
    assert data_2_after["missing_count"] == 1

    income_item_2 = next(d for d in data_2_after["documents"] if d["standard_type"] == "Income Certificate")
    assert income_item_2["matched_document_id"] == doc_id

    # Scheme-specific requirement preserved!
    aicte_item = next(d for d in data_2_after["documents"] if "AICTE" in d["document_name"])
    assert aicte_item["status"] == "missing"
    assert aicte_item["original_text"] == "AICTE admission letter"


def test_document_verification_workflow_and_role_authorization(isolated_client, tmp_path, monkeypatch):
    """Students cannot verify documents; only authorized counselors/admins can verify or reject."""
    monkeypatch.setattr("app.core.config.settings.storage_local_dir", str(tmp_path))
    student_id, token, student_headers = create_test_student_with_token(isolated_client)
    counselor_headers = make_counselor_headers()

    # Upload document
    files = {"file": ("caste.pdf", make_dummy_pdf(), "application/pdf")}
    upload_res = isolated_client.post(
        "/api/student/documents/upload",
        data={"student_id": student_id, "document_type": "Caste Certificate", "run_ocr": "false"},
        files=files,
        headers=student_headers,
    )
    doc_id = upload_res.json()["id"]
    assert upload_res.json()["verification_status"] == "pending_review"

    # 1. Unauthenticated request to verify endpoint is rejected with 401
    res = isolated_client.patch(
        f"/api/counselor/documents/{doc_id}/verify",
        json={"verification_status": "verified"},
    )
    assert res.status_code == 401

    # 2. Student attempting to self-verify is rejected with 403 Forbidden
    student_verify = isolated_client.patch(
        f"/api/counselor/documents/{doc_id}/verify",
        json={"verification_status": "verified"},
        headers=student_headers,
    )
    assert student_verify.status_code == 403
    assert "Forbidden" in student_verify.json()["detail"]

    # 3. Authorized reviewer marks as verified -> 200 OK
    verify_res = isolated_client.patch(
        f"/api/counselor/documents/{doc_id}/verify",
        json={"verification_status": "verified"},
        headers=counselor_headers,
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["verification_status"] == "verified"
    assert verify_res.json()["verified_at"] is not None

    # 4. Authorized reviewer rejects document with reason -> 200 OK
    reject_res = isolated_client.patch(
        f"/api/counselor/documents/{doc_id}/verify",
        json={"verification_status": "rejected", "rejection_reason": "Blurred stamp"},
        headers=counselor_headers,
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["verification_status"] == "rejected"
    assert reject_res.json()["rejection_reason"] == "Blurred stamp"


def test_storage_service_production_enforcement(monkeypatch, tmp_path):
    """In production, missing Supabase credentials raises StorageError and prohibits local fallback."""
    service = StorageService()
    service.is_supabase_configured = False
    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(StorageError, match="Production environment requires Supabase Storage"):
        service.upload_file("test.pdf", b"content")

    with pytest.raises(StorageError, match="Production environment requires Supabase Storage"):
        service.download_file("test.pdf")

    with pytest.raises(StorageError, match="Production environment requires Supabase Storage"):
        service.create_signed_url("test.pdf")

    with pytest.raises(StorageError, match="Production environment requires Supabase Storage"):
        service.delete_file("test.pdf")
