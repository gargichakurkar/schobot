from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReminderPreference(Base):
    __tablename__ = "reminder_preferences"
    __table_args__ = (UniqueConstraint("student_id", "scholarship_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("student_profiles.id"), nullable=False)
    scholarship_id: Mapped[str] = mapped_column(String(36), ForeignKey("scholarships.id"), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
