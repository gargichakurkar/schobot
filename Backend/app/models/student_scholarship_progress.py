from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudentScholarshipProgress(Base):
    __tablename__ = "student_scholarship_progress"
    __table_args__ = (
        UniqueConstraint("student_id", "scholarship_id", name="uq_student_scholarship_progress"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    student_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("student_profiles.id"),
        nullable=False,
        index=True,
    )
    scholarship_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scholarships.id"),
        nullable=False,
        index=True,
    )
    doc_status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_started")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
