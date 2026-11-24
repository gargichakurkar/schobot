from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

ALGORITHM = "HS256"
MINIMUM_SIGNING_KEY_LENGTH = 32

ACCESS_TOKEN_EXPIRE_MINUTES = 60


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)


def _jwt_signing_key() -> str:
    key = settings.secret_key
    if len(key) < MINIMUM_SIGNING_KEY_LENGTH:
        raise RuntimeError(
            "SECRET_KEY must be configured with at least 32 characters before signing JWTs."
        )
    return key


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    return pwd_context.verify(
        plain_password,
        hashed_password
    )


def create_access_token(
    data: dict,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES
):
    payload = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        _jwt_signing_key(),
        algorithm=ALGORITHM
    )