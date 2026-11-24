from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
)

from app.core.database import Base


class ScholarshipIngestionSource(Base):
    __tablename__ = "scholarship_ingestion_sources"

    source_key = Column(String(64), primary_key=True)
    name = Column(String(160), nullable=False)
    listing_url = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)
    last_started_at = Column(DateTime(timezone=True), nullable=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)


class ScholarshipIngestionState(Base):
    __tablename__ = "scholarship_ingestion_state"

    source_key = Column(String(64), primary_key=True)
    source_identifier = Column(String(255), primary_key=True)
    scholarship_id = Column(String(36), nullable=True)
    source_url = Column(Text, nullable=True)
    guideline_url = Column(Text, nullable=True)
    resolved_guideline_url = Column(Text, nullable=True)
    listing_hash = Column(String(64), nullable=True)
    document_hash = Column(String(64), nullable=True)
    content_hash = Column(String(64), nullable=True)
    etag = Column(String(512), nullable=True)
    last_modified = Column(String(255), nullable=True)
    dataset_fields = Column(JSON, nullable=False, default=dict)
    source_text = Column(Text, nullable=True)
    extraction_status = Column(String(32), nullable=False, default="pending")
    classification = Column(String(32), nullable=False, default="NEW")
    application_status = Column(String(32), nullable=False, default="unknown")
    application_deadline = Column(String(20), nullable=True)
    deadline_evidence = Column(Text, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_extracted_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)


class ScholarshipIngestionRun(Base):
    __tablename__ = "scholarship_ingestion_runs"

    id = Column(String(36), primary_key=True)
    source_key = Column(String(64), nullable=False, index=True)
    source_url = Column(Text, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, default="running")
    statistics = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)


class ScholarshipIngestionEvent(Base):
    __tablename__ = "scholarship_ingestion_events"

    id = Column(String(36), primary_key=True)
    run_id = Column(
        String(36),
        ForeignKey("scholarship_ingestion_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_key = Column(String(64), nullable=False, index=True)
    source_identifier = Column(String(255), nullable=True)
    scholarship_id = Column(String(36), nullable=True)
    classification = Column(String(32), nullable=False)
    source_url = Column(Text, nullable=True)
    guideline_url = Column(Text, nullable=True)
    resolved_guideline_url = Column(Text, nullable=True)
    listing_hash = Column(String(64), nullable=True)
    document_hash = Column(String(64), nullable=True)
    extracted_fields = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
