from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScholarshipMatch(Base):
    __tablename__ = "scholarship_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("student_profiles.id"), nullable=False)
    scholarship_id: Mapped[str] = mapped_column(String(36), ForeignKey("scholarships.id"), nullable=False)
    match_status: Mapped[str] = mapped_column(String(50), nullable=False, default="needs_verification")
    match_score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    passed_rules: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    failed_rules: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    unknown_rules: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    student: Mapped["StudentProfile"] = relationship(back_populates="scholarship_matches")
    scholarship: Mapped["Scholarship"] = relationship(back_populates="scholarship_matches")
