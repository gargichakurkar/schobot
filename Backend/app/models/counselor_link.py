from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CounselorLink(Base):
    __tablename__ = "counselor_links"
    __table_args__ = (UniqueConstraint("student_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("student_profiles.id"), nullable=False)
    counselor_email: Mapped[str] = mapped_column(String(255), nullable=False)
    counselor_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="en")
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=lambda: datetime.now(timezone.utc) + timedelta(days=30),
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
