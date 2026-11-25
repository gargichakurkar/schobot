from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentBase(BaseModel):
    student_id: str | None = None
    document_type: str | None = None
    file_name: str | None = None
    extracted_text: str | None = None


class DocumentResponse(DocumentBase):
    id: str


class VaultDocumentResponse(BaseModel):
    id: str
    student_id: str
    document_type: str
    original_filename: str
    storage_path: str
    mime_type: str
    file_size: int
    ocr_status: str
    extracted_text: str | None = None
    extracted_fields: dict[str, Any] | None = None
    verification_status: str
    expiry_date: datetime | None = None
    rejection_reason: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    download_url: str | None = None

    model_config = ConfigDict(from_attributes=True)


class VaultDocumentListResponse(BaseModel):
    student_id: str
    documents: list[VaultDocumentResponse]
    total: int


class ScholarshipDocumentRequirementItem(BaseModel):
    document_name: str
    standard_type: str
    original_text: str
    is_standard: bool
    is_fallback: bool = False
    status: str  # missing, uploaded, pending_review, verified, rejected, expired
    matched_document_id: str | None = None
    matched_document_filename: str | None = None
    verification_status: str = "missing"
    notes: str | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class DynamicScholarshipDocumentsResponse(BaseModel):
    student_id: str
    scholarship_id: str
    scholarship_name: str
    required_count: int
    available_count: int
    missing_count: int
    documents: list[ScholarshipDocumentRequirementItem]
    official_required_documents_text: str | None = None


class DocumentVerificationUpdate(BaseModel):
    verification_status: str  # "verified", "rejected", "pending_review"
    rejection_reason: str | None = None
