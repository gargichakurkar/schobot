from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.models.student_scholarship_document import StudentScholarshipDocument
from app.schemas.document import (
    DynamicScholarshipDocumentsResponse,
    ScholarshipDocumentRequirementItem,
    VaultDocumentResponse,
)
from app.services.ocr_service import (
    InvalidDocumentError,
    OCRService,
    OCRUnavailableError,
)
from app.services.storage_service import StorageError, StorageService, get_storage_service
from app.utils.document_standards import (
    StandardDocumentType,
    normalize_document_type,
    parse_scholarship_required_documents,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB limit
_SUPPORTED_MAGIC_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}

_FIELD_PATTERNS = {
    "applicant_name": re.compile(
        r"^\s*(?:applicant(?:'s)?\s+name|name\s+of\s+(?:the\s+)?applicant)\s*[:\-]\s*(.{2,100})\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "certificate_number": re.compile(
        r"^\s*(?:certificate\s*(?:no\.?|number|id))\s*[:\-]\s*([A-Z0-9/\-]{2,80})\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "issue_date": re.compile(
        r"^\s*(?:date\s+of\s+issue|issued\s+on)\s*[:\-]\s*([A-Z0-9,./\- ]{4,40})\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "issuing_authority": re.compile(
        r"^\s*(?:issuing\s+authority|issued\s+by)\s*[:\-]\s*(.{2,120})\s*$",
        re.IGNORECASE | re.MULTILINE,
    ),
}


def sanitize_filename(filename: str) -> str:
    clean = re.sub(r"[^\w.\-]", "_", os.path.basename(filename))
    return clean[:100] or "document"


class DocumentVaultService:
    def __init__(
        self,
        db: Session,
        storage_service: StorageService | None = None,
        ocr_service: OCRService | None = None,
    ) -> None:
        self.db = db
        self.storage = storage_service or get_storage_service()
        self.ocr_service = ocr_service or OCRService()

    def get_student_documents(self, student_id: str) -> list[VaultDocumentResponse]:
        """Fetch all vault documents for the authenticated student."""
        docs = (
            self.db.query(Document)
            .filter(Document.student_id == student_id)
            .order_by(Document.created_at.desc())
            .all()
        )
        results = []
        for doc in docs:
            resp = VaultDocumentResponse.model_validate(doc)
            resp.download_url = self.storage.create_signed_url(doc.storage_path)
            results.append(resp)
        return results

    def upload_document(
        self,
        *,
        student_id: str,
        document_type: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        run_ocr: bool = True,
    ) -> VaultDocumentResponse:
        """Validate, store, process OCR, and save document to the student's central vault."""
        student = self.db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
        if student is None:
            raise HTTPException(status_code=404, detail="Student profile not found")

        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")
        if not file_bytes:
            raise HTTPException(status_code=422, detail="The uploaded file is empty.")

        # Validate file extension and magic signatures
        ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        supported = _SUPPORTED_MAGIC_TYPES.get(ext)
        if not supported:
            raise HTTPException(status_code=415, detail="Only PDF, JPG, and PNG files are supported.")

        expected_mime, magic_sig = supported
        if not file_bytes.startswith(magic_sig):
            raise HTTPException(status_code=422, detail="File contents do not match a supported file format.")

        resolved_mime = content_type or expected_mime
        clean_name = sanitize_filename(filename)
        storage_filename = f"{uuid4().hex}_{clean_name}"
        storage_path = f"students/{student_id}/{storage_filename}"

        # 1. Store in Supabase / Local storage
        try:
            self.storage.upload_file(storage_path, file_bytes, resolved_mime)
        except StorageError as exc:
            logger.error("Failed to upload document file: %s", exc)
            raise HTTPException(status_code=502, detail=f"Storage upload failed: {exc}") from exc

        # 2. Process OCR if requested
        ocr_status = "not_processed"
        extracted_text = None
        extracted_fields: dict[str, Any] = {}

        if run_ocr:
            try:
                ocr_result = self.ocr_service.extract_text(file_bytes, expected_mime)
                extracted_text = ocr_result.text
                ocr_status = "completed"

                # Parse structured fields
                for field_name, pattern in _FIELD_PATTERNS.items():
                    matches = []
                    for match in pattern.finditer(extracted_text):
                        val = re.sub(r"\s+", " ", match.group(1)).strip(" \t:;,.")
                        if val and val not in matches:
                            matches.append(val)
                    if matches:
                        extracted_fields[field_name] = matches[0]

            except (OCRUnavailableError, InvalidDocumentError) as exc:
                logger.info("OCR extraction skipped or unavailable: %s", exc)
                ocr_status = "failed"
            except Exception as exc:
                logger.warning("OCR processing error: %s", exc)
                ocr_status = "failed"

        # 3. Create Document record in database
        standard_type = normalize_document_type(document_type)
        doc = Document(
            student_id=student_id,
            document_type=standard_type,
            original_filename=clean_name,
            file_name=clean_name,
            storage_path=storage_path,
            mime_type=resolved_mime,
            file_size=len(file_bytes),
            ocr_status=ocr_status,
            extracted_text=extracted_text,
            extracted_fields=extracted_fields or None,
            verification_status="pending_review",  # uploaded documents begin as pending_review
        )

        try:
            self.db.add(doc)
            self.db.commit()
            self.db.refresh(doc)
        except Exception as exc:
            self.db.rollback()
            # Clean up uploaded storage file on DB error
            self.storage.delete_file(storage_path)
            logger.error("Database save failed for document: %s", exc)
            raise HTTPException(status_code=500, detail="Failed to save document metadata.") from exc

        resp = VaultDocumentResponse.model_validate(doc)
        resp.download_url = self.storage.create_signed_url(doc.storage_path)
        return resp

    def get_document(self, student_id: str, document_id: str) -> VaultDocumentResponse:
        """Fetch a specific vault document ensuring ownership."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if doc.student_id != student_id:
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to access this document.")
        resp = VaultDocumentResponse.model_validate(doc)
        resp.download_url = self.storage.create_signed_url(doc.storage_path)
        return resp

    def download_document(self, student_id: str, document_id: str) -> tuple[bytes, str, str]:
        """Download document bytes ensuring ownership."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if doc.student_id != student_id:
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to download this document.")
        try:
            content = self.storage.download_file(doc.storage_path)
            return content, doc.mime_type, doc.original_filename
        except StorageError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    def delete_document(self, student_id: str, document_id: str) -> dict[str, Any]:
        """Delete document from vault and storage."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if doc.student_id != student_id:
            raise HTTPException(status_code=403, detail="Forbidden: You do not have permission to delete this document.")

        storage_path = doc.storage_path
        self.db.delete(doc)
        self.db.commit()

        # Delete from storage backend
        self.storage.delete_file(storage_path)
        return {"deleted": True, "id": document_id}

    def match_documents_for_scholarship(
        self,
        student_id: str,
        scholarship_id: str,
    ) -> DynamicScholarshipDocumentsResponse:
        """Dynamically evaluate scholarship required documents against student's Document Vault."""
        student = self.db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
        if student is None:
            raise HTTPException(status_code=404, detail="Student profile not found")

        scholarship = self.db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
        if scholarship is None:
            raise HTTPException(status_code=404, detail="Scholarship not found")

        # 1. Parse scholarship-specific requirements
        requirements = parse_scholarship_required_documents(scholarship.required_documents)

        # 2. Fetch all student vault documents
        vault_docs = (
            self.db.query(Document)
            .filter(Document.student_id == student_id)
            .order_by(Document.created_at.desc())
            .all()
        )
        vault_by_type: dict[str, list[Document]] = {}
        for d in vault_docs:
            vault_by_type.setdefault(d.document_type, []).append(d)

        # 3. Fetch any existing student scholarship document notes
        saved_notes = {
            ssd.document_name: ssd
            for ssd in self.db.query(StudentScholarshipDocument)
            .filter(
                StudentScholarshipDocument.student_id == student_id,
                StudentScholarshipDocument.scholarship_id == scholarship_id,
            )
            .all()
        }

        # 4. Compare requirements against vault
        checklist_items: list[ScholarshipDocumentRequirementItem] = []
        available_count = 0
        missing_count = 0

        for req in requirements:
            std_type = req["standard_type"]
            doc_name = req["document_name"]
            saved_meta = saved_notes.get(doc_name)

            # Find matching document in vault by standard type or exact name
            matching_doc = None
            if std_type in vault_by_type and vault_by_type[std_type]:
                matching_doc = vault_by_type[std_type][0]
            else:
                for v in vault_docs:
                    if v.original_filename.lower() == doc_name.lower():
                        matching_doc = v
                        break

            if matching_doc is not None:
                # Check status
                v_status = matching_doc.verification_status
                if v_status == "verified":
                    status = "verified"
                    available_count += 1
                elif v_status == "rejected":
                    status = "rejected"
                    missing_count += 1
                elif v_status == "expired":
                    status = "expired"
                    missing_count += 1
                elif v_status == "pending_review":
                    status = "pending_review"
                    available_count += 1
                else:
                    status = "uploaded"
                    available_count += 1

                item = ScholarshipDocumentRequirementItem(
                    document_name=doc_name,
                    standard_type=std_type,
                    original_text=req["original_text"],
                    is_standard=req["is_standard"],
                    is_fallback=req.get("is_fallback", False),
                    status=status,
                    matched_document_id=matching_doc.id,
                    matched_document_filename=matching_doc.original_filename,
                    verification_status=v_status,
                    notes=saved_meta.notes if saved_meta else None,
                    updated_at=matching_doc.updated_at,
                )
            else:
                status = "missing"
                missing_count += 1
                item = ScholarshipDocumentRequirementItem(
                    document_name=doc_name,
                    standard_type=std_type,
                    original_text=req["original_text"],
                    is_standard=req["is_standard"],
                    is_fallback=req.get("is_fallback", False),
                    status=status,
                    matched_document_id=None,
                    matched_document_filename=None,
                    verification_status="missing",
                    notes=saved_meta.notes if saved_meta else None,
                    updated_at=saved_meta.updated_at if saved_meta else None,
                )

            checklist_items.append(item)

        return DynamicScholarshipDocumentsResponse(
            student_id=student_id,
            scholarship_id=scholarship_id,
            scholarship_name=scholarship.scholarship_name,
            required_count=len(checklist_items),
            available_count=available_count,
            missing_count=missing_count,
            documents=checklist_items,
            official_required_documents_text=scholarship.required_documents,
        )

    def verify_document(
        self,
        document_id: str,
        verification_status: str,
        rejection_reason: str | None = None,
        reviewer_id: str | None = None,
    ) -> VaultDocumentResponse:
        """Authorized reviewer endpoint to verify or reject a document."""
        if verification_status not in ("verified", "rejected", "pending_review", "expired"):
            raise HTTPException(status_code=422, detail=f"Invalid verification status: {verification_status}")

        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")

        doc.verification_status = verification_status
        doc.rejection_reason = rejection_reason if verification_status == "rejected" else None
        doc.verified_by = reviewer_id or "counselor"
        doc.verified_at = datetime.now(timezone.utc) if verification_status == "verified" else None

        self.db.commit()
        self.db.refresh(doc)

        resp = VaultDocumentResponse.model_validate(doc)
        resp.download_url = self.storage.create_signed_url(doc.storage_path)
        return resp
