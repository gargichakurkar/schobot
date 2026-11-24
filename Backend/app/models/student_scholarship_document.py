from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudentScholarshipDocument(Base):
    __tablename__ = "student_scholarship_documents"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "scholarship_id",
            "document_name",
            name="uq_student_scholarship_document",
        ),
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
    document_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_uploaded")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
