from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.student_profile import StudentProfile

ALGORITHM = "HS256"
MINIMUM_SIGNING_KEY_LENGTH = 32

ACCESS_TOKEN_EXPIRE_MINUTES = 60


def _init_pwd_context() -> CryptContext:
    try:
        ctx = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")
        ctx.hash("test-probe")
        return ctx
    except Exception:
        return CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


pwd_context = _init_pwd_context()


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


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, _jwt_signing_key(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.JWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials: invalid token signature.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_student(
    request: Request,
    authorization: str | None = Header(None),
    x_student_token: str | None = Header(None),
    db: Session = Depends(get_db),
) -> StudentProfile:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    elif x_student_token:
        token = x_student_token.strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    student_id = payload.get("sub")
    role = payload.get("role")
    if not student_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: missing student identifier.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if role != "student":
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Access token does not have the student role.",
        )

    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(
            status_code=401,
            detail="Authenticated student account does not exist.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return student


def require_counselor_or_admin(
    request: Request,
    authorization: str | None = Header(None),
    x_counselor_token: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict:
    # 1. Check counselor link token header
    if x_counselor_token:
        from datetime import datetime, timezone
        from app.models.counselor_link import CounselorLink

        link = db.query(CounselorLink).filter(CounselorLink.token == x_counselor_token).first()
        if link:
            if getattr(link, "is_revoked", False):
                raise HTTPException(
                    status_code=403,
                    detail="Counselor link has been revoked by the student.",
                )
            exp = getattr(link, "expires_at", None)
            if exp:
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp < datetime.now(timezone.utc):
                    raise HTTPException(
                        status_code=403,
                        detail="Counselor access link has expired.",
                    )
            return {"role": "counselor", "identifier": link.counselor_email}

    # 2. Check JWT Bearer token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_access_token(token)
        role = payload.get("role")
        if role in ("counselor", "admin"):
            return {"role": role, "identifier": payload.get("sub")}
        else:
            raise HTTPException(
                status_code=403,
                detail="Forbidden: Student accounts cannot review, verify, or reject documents.",
            )

    raise HTTPException(
        status_code=401,
        detail="Authentication required: Counselor or administrator credentials missing.",
        headers={"WWW-Authenticate": "Bearer"},
    )