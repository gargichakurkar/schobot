from __future__ import annotations

import logging
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.student_profile import StudentProfile
from app.schemas.student_profile import (
    RequestOTPRequest,
    StudentLoginRequest,
    StudentProfileCreate,
    StudentProfileResponse,
    StudentProfileUpdate,
    VerifyOTPSetPasswordRequest,
)
from app.services.email_service import EmailNotConfiguredError, get_email_service
from app.services.profile_service import ProfileService
from auth import create_access_token, get_current_student, hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["profiles"])

_OTP_LIMITER: dict[str, list[float]] = defaultdict(list)
_OTP_LIMITER_LOCK = Lock()
_OTP_WINDOW = 300.0  # 5 minutes
_OTP_MAX_PER_WINDOW = 4
_OTP_COOLDOWN = 15.0  # 15 seconds cooldown between successive clicks


@router.post("/profiles", response_model=StudentProfileResponse)
def create_profile(payload: StudentProfileCreate, db: Session = Depends(get_db)) -> StudentProfileResponse:
    if not payload.password:
        raise HTTPException(
            status_code=422,
            detail="Password is required for student registration (minimum 10 characters).",
        )
    service = ProfileService(db)
    try:
        profile = service.create_profile(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    resp = StudentProfileResponse.model_validate(profile)
    try:
        resp.access_token = create_access_token({"sub": profile.id, "role": "student"})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Profile created but token generation failed.") from exc
    return resp


@router.post("/auth/token")
def issue_student_token(payload: StudentLoginRequest, db: Session = Depends(get_db)) -> dict:
    identifier = (payload.identifier or payload.email or payload.student_id or "").strip()
    password = payload.password

    student = db.query(StudentProfile).filter(
        (StudentProfile.id == identifier) | (func.lower(StudentProfile.email) == identifier.lower())
    ).first()

    # Generic credential rejection to prevent account enumeration
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials. Please check your email/student ID and password.")

    if not student.password_hash:
        raise HTTPException(
            status_code=403,
            detail=(
                "Account activation required. Your account does not have a password set yet. "
                "Please use the 'Activate Account / Forgot Password' flow to set your password via email verification."
            ),
        )

    if not verify_password(password, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials. Please check your email/student ID and password.")

    token = create_access_token({"sub": student.id, "role": "student"})
    student_data = StudentProfileResponse.model_validate(student)
    student_data.access_token = token
    return {
        "access_token": token,
        "token_type": "bearer",
        "student_id": student.id,
        "student": student_data,
    }


@router.post("/auth/request-otp")
def request_otp(payload: RequestOTPRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    identifier = payload.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=422, detail="Identifier is required.")

    # Rate-limit OTP requests by account and IP
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    rate_key = f"{client_ip}:{identifier.lower()}"
    with _OTP_LIMITER_LOCK:
        history = _OTP_LIMITER[rate_key]
        _OTP_LIMITER[rate_key] = [t for t in history if now - t < _OTP_WINDOW]
        history = _OTP_LIMITER[rate_key]
        if history and (now - history[-1]) < _OTP_COOLDOWN:
            raise HTTPException(
                status_code=429,
                detail="Please wait a few seconds before requesting another verification code.",
            )
        if len(history) >= _OTP_MAX_PER_WINDOW:
            raise HTTPException(
                status_code=429,
                detail="Too many verification requests. Please wait a few minutes before trying again.",
            )
        history.append(now)

    student = db.query(StudentProfile).filter(
        (StudentProfile.id == identifier) | (func.lower(StudentProfile.email) == identifier.lower())
    ).first()

    # Account-enumeration protection: return generic response without sending email
    if not student or not student.email:
        parts = identifier.split("@") if "@" in identifier else [identifier, ""]
        masked_email = f"{parts[0][:2]}***@{parts[1]}" if len(parts[0]) > 2 and parts[1] else "***"
        return {
            "status": "success",
            "message": "If an account exists for this identifier, a verification code has been sent.",
            "masked_email": masked_email,
        }

    # Database-level cooldown check against student.otp_expires_at
    now_utc = datetime.now(timezone.utc)
    if student.otp_expires_at:
        exp = student.otp_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        issued_at = exp - timedelta(minutes=10)
        if (now_utc - issued_at).total_seconds() < _OTP_COOLDOWN:
            raise HTTPException(
                status_code=429,
                detail="Please wait a few seconds before requesting another verification code.",
            )

    # Invalidate previous OTP and store new hashed OTP
    otp = f"{secrets.randbelow(1000000):06d}"
    student.otp_hash = hash_password(otp)
    student.otp_expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    student.otp_attempts = 0
    db.commit()

    email_service = get_email_service()
    try:
        email_service.send_otp_email(student.email, otp)
    except EmailNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Email delivery service is not configured on this server. "
                "SMTP configuration (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD) must be provided in Render environment variables."
            ),
        ) from exc
    except Exception as exc:
        logger.error("Failed to deliver verification email to %s: %s", student.email, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to deliver verification email. Please try again later or contact support.",
        ) from exc

    parts = student.email.split("@")
    masked_email = f"{parts[0][:2]}***@{parts[1]}" if len(parts[0]) > 2 else f"{parts[0][:1]}***@{parts[1]}"
    return {
        "status": "success",
        "message": "If an account exists for this identifier, a verification code has been sent.",
        "masked_email": masked_email,
    }


@router.post("/auth/verify-otp-set-password")
def verify_otp_set_password(payload: VerifyOTPSetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    identifier = payload.identifier.strip()
    student = db.query(StudentProfile).filter(
        (StudentProfile.id == identifier) | (func.lower(StudentProfile.email) == identifier.lower())
    ).first()

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found.")

    if not student.otp_hash or not student.otp_expires_at:
        raise HTTPException(
            status_code=400,
            detail="No pending verification request found for this account. Please request a new code.",
        )

    now_utc = datetime.now(timezone.utc)
    expires_at = student.otp_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at and now_utc > expires_at:
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired. Please request a new code.",
        )

    if (student.otp_attempts or 0) >= 5:
        raise HTTPException(
            status_code=429,
            detail="Too many invalid verification attempts. Please request a new code.",
        )

    if not verify_password(payload.otp.strip(), student.otp_hash):
        student.otp_attempts = (student.otp_attempts or 0) + 1
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid verification code. Please check and try again.")

    # Valid OTP! Update password and clear OTP
    student.password_hash = hash_password(payload.new_password)
    student.otp_hash = None
    student.otp_expires_at = None
    student.otp_attempts = 0
    db.commit()
    db.refresh(student)

    token = create_access_token({"sub": student.id, "role": "student"})
    student_data = StudentProfileResponse.model_validate(student)
    student_data.access_token = token
    return {
        "status": "success",
        "message": "Password successfully set. You are now logged in.",
        "access_token": token,
        "token_type": "bearer",
        "student_id": student.id,
        "student": student_data,
    }


@router.get("/auth/status")
def get_auth_status() -> dict:
    return {
        "email_configured": get_email_service().is_configured,
    }


@router.get("/profiles/{student_id}", response_model=StudentProfileResponse)
def get_profile(
    student_id: str,
    db: Session = Depends(get_db),
    current_student: StudentProfile = Depends(get_current_student),
) -> StudentProfileResponse:
    if current_student.id != student_id:
        raise HTTPException(status_code=403, detail="You cannot access another student's profile.")

    service = ProfileService(db)
    profile = service.get_profile(student_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return profile


@router.put("/profiles/{student_id}", response_model=StudentProfileResponse)
def update_profile(
    student_id: str,
    payload: StudentProfileUpdate,
    db: Session = Depends(get_db),
    current_student: StudentProfile = Depends(get_current_student),
) -> StudentProfileResponse:
    if current_student.id != student_id:
        raise HTTPException(status_code=403, detail="You cannot update another student's profile.")

    service = ProfileService(db)
    try:
        profile = service.update_profile(student_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile
