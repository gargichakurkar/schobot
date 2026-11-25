from __future__ import annotations

import re

from app.services.certificate_knowledge import CertificateType, retrieve_sources
from app.services.ocr_service import (
    InvalidDocumentError,
    OCRService,
)


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_SUPPORTED_FILES = {
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


class UploadTooLargeError(ValueError):
    pass


class UnsupportedMediaTypeError(ValueError):
    pass


class DocumentService:
    def __init__(self, db=None, ocr_service: OCRService | None = None) -> None:
        self.db = db
        self.ocr_service = ocr_service or OCRService()

    def scan_document(
        self,
        *,
        certificate_type: CertificateType,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> dict:
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise UploadTooLargeError("File exceeds the 10 MB upload limit.")
        if not file_bytes:
            raise InvalidDocumentError("The uploaded file is empty.")

        suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        supported_file = _SUPPORTED_FILES.get(suffix)
        if supported_file is None:
            raise UnsupportedMediaTypeError("Only PDF, JPG and PNG files are supported.")

        expected_type, signature = supported_file
        if content_type and content_type not in (expected_type, "application/octet-stream"):
            raise UnsupportedMediaTypeError("The uploaded file type does not match its content.")
        if not file_bytes.startswith(signature):
            raise InvalidDocumentError("The file contents do not match a supported file format.")

        extracted = self.ocr_service.extract_text(file_bytes, expected_type)
        fields: dict[str, dict[str, str | None]] = {}
        missing_information = []
        uncertain_fields = []
        possible_inconsistencies = []

        for field_name, pattern in _FIELD_PATTERNS.items():
            matches = []
            for match in pattern.finditer(extracted.text):
                value = re.sub(r"\s+", " ", match.group(1)).strip(" \t:;,.")
                if value and value not in matches:
                    matches.append(value)
            if not matches:
                fields[field_name] = {
                    "value": None,
                    "status": "not_detected",
                    "evidence": None,
                }
                missing_information.append(field_name)
                continue

            evidence_value = matches[0]
            fields[field_name] = {
                "value": evidence_value,
                "status": "needs_review",
                "evidence": evidence_value,
            }
            uncertain_fields.append(field_name)
            if len(matches) > 1:
                possible_inconsistencies.append(
                    {
                        "field": field_name,
                        "message": "Multiple different values were detected; please compare them with the original.",
                    }
                )

        sources = retrieve_sources(
            certificate_type,
            query=(
                f"{certificate_type.value} certificate official guidance "
                f"application evidence {extracted.text[:5000]}"
            ),
        )
        return {
            "status": "needs_manual_review",
            "certificate_type": certificate_type.value,
            "fields": fields,
            "missing_information": missing_information,
            "uncertain_fields": uncertain_fields,
            "possible_inconsistencies": possible_inconsistencies,
            "source_references": sources,
            "extraction": {
                "method": extracted.method,
                "pages_processed": extracted.pages_processed,
                "warnings": list(extracted.warnings),
            },
            "requirement_check": {
                "status": "not_evaluated",
                "message": (
                    "Relevant passages are retrieved from the approved official source "
                    "corpus. The available sources do not define a complete issued-certificate "
                    "field standard, so requirements are not evaluated."
                ),
            },
            "limitations": [
                "OCR text and detected fields may be incorrect; review them against the original.",
                "This scan does not verify authenticity, digital signatures, QR codes or legal validity.",
                "The uploaded certificate, extracted text and corrections are not persisted or indexed.",
            ],
        }
