from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    education_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    course: Mapped[str | None] = mapped_column(String(150), nullable=True)
    study_year: Mapped[str | None] = mapped_column(String(50), nullable=True)
    college_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    academic_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    domicile_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    study_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Disability-related information
    disability_percentage: Mapped[float | None] = mapped_column(Float, nullable=True, default=None)
    has_valid_disability_certificate: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    has_udid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    # Swanath-related information
    is_orphan: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    parent_death_due_to_covid: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    parent_martyred_armed_forces: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)

    # Railway scholarship information
    is_dependent_of_rpf_rpsf: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    parent_service_category: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    # Academic and other scholarship conditions
    previous_year_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    receives_other_scholarship: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    has_disability_certificate: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    annual_family_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_income_certificate: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=False)
    profile_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    otp_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    otp_attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    scholarship_matches: Mapped[list["ScholarshipMatch"]] = relationship(back_populates="student")
    documents: Mapped[list["Document"]] = relationship(back_populates="student", cascade="all, delete-orphan")
