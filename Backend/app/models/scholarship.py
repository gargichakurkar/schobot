from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    dataset_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    scholarship_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_category_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    income_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_income_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_documents: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scheme_info_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scholarship_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    min_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimum_marks_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_education_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligible_level: Mapped[str | None] = mapped_column(String(150), nullable=True)
    eligible_course: Mapped[str | None] = mapped_column(String(150), nullable=True)
    gender_requirement: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_filename: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    milestones: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    scholarship_matches: Mapped[list["ScholarshipMatch"]] = relationship(back_populates="scholarship")
