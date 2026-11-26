from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from auth import (
    create_access_token,
    decode_access_token,
    get_current_student,
    hash_password,
    require_counselor_or_admin,
    verify_password,
)


def test_access_token_requires_configured_signing_key(monkeypatch):
    monkeypatch.setattr(settings, "secret_key", "")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_access_token({"sub": "synthetic-student"})


def test_access_token_uses_configured_signing_key(monkeypatch):
    key = "test-only-signing-key-with-adequate-length"
    monkeypatch.setattr(settings, "secret_key", key)

    token = create_access_token({"sub": "synthetic-student"})

    decoded = jwt.decode(token, key, algorithms=["HS256"])
    assert decoded["sub"] == "synthetic-student"


def test_password_hashing_and_verification():
    raw = "MySecretPass123!"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("WrongPass", hashed) is False


def test_decode_access_token_expired(monkeypatch):
    key = "test-only-signing-key-with-adequate-length"
    monkeypatch.setattr(settings, "secret_key", key)

    # Token with exp in the past
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode({"sub": "s1", "exp": past}, key, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_decode_access_token_tampered(monkeypatch):
    key = "test-only-signing-key-with-adequate-length"
    monkeypatch.setattr(settings, "secret_key", key)

    token = create_access_token({"sub": "s1", "role": "student"})
    tampered_token = token[:-5] + "aaaaa"

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(tampered_token)
    assert exc_info.value.status_code == 401
    assert "invalid token signature" in exc_info.value.detail.lower()


def test_counselor_guard_rejects_student_role(monkeypatch):
    key = "test-only-signing-key-with-adequate-length"
    monkeypatch.setattr(settings, "secret_key", key)

    student_token = create_access_token({"sub": "student-123", "role": "student"})

    with pytest.raises(HTTPException) as exc_info:
        require_counselor_or_admin(
            request=None,
            authorization=f"Bearer {student_token}",
            x_counselor_token=None,
            db=None,
        )
    assert exc_info.value.status_code == 403
    assert "Forbidden" in exc_info.value.detail


def test_counselor_guard_accepts_admin_role(monkeypatch):
    key = "test-only-signing-key-with-adequate-length"
    monkeypatch.setattr(settings, "secret_key", key)

    admin_token = create_access_token({"sub": "admin-123", "role": "admin"})

    res = require_counselor_or_admin(
        request=None,
        authorization=f"Bearer {admin_token}",
        x_counselor_token=None,
        db=None,
    )
    assert res["role"] == "admin"
    assert res["identifier"] == "admin-123"
