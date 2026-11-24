import pytest
from jose import jwt

from app.core.config import settings
from auth import create_access_token


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
