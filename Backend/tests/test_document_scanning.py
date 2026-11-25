from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.main import app
from app.routers.documents import get_document_service
from app.services.certificate_knowledge import (
    CertificateType,
    retrieve_sources,
    source_manifest,
)
from app.services.document_service import DocumentService
from app.services.ocr_service import OCRResult, OCRService, OCRUnavailableError


class StubOCRService:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self, file_bytes: bytes, file_type: str) -> OCRResult:
        return OCRResult(
            text=self.text,
            method="test",
            pages_processed=1,
        )


@pytest.mark.parametrize("certificate_type", [item.value for item in CertificateType])
def test_scan_supports_only_the_five_certificate_types(isolated_client, certificate_type):
    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        ocr_service=StubOCRService("Applicant Name: Sample Student")
    )
    try:
        response = isolated_client.post(
            "/api/documents/scan",
            data={"certificate_type": certificate_type},
            files={"file": ("certificate.pdf", b"%PDF-1.7 sample", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_document_service, None)

    assert response.status_code == 200, response.text
    assert response.json()["certificate_type"] == certificate_type
    assert response.json()["status"] == "needs_manual_review"


def test_scan_extracts_candidates_and_marks_them_for_manual_review(isolated_client):
    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        ocr_service=StubOCRService(
            "Applicant Name: Sample Student\n"
            "Certificate Number: MH-1234\n"
            "Date of Issue: 12/01/2025\n"
            "Issuing Authority: Tahsildar"
        )
    )
    try:
        response = isolated_client.post(
            "/api/documents/scan",
            data={"certificate_type": CertificateType.INCOME.value},
            files={"file": ("certificate.pdf", b"%PDF-1.7 sample", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_document_service, None)

    data = response.json()
    assert response.status_code == 200
    assert data["fields"]["applicant_name"]["value"] == "Sample Student"
    assert data["fields"]["certificate_number"]["value"] == "MH-1234"
    assert data["fields"]["applicant_name"]["status"] == "needs_review"
    assert data["requirement_check"]["status"] == "not_evaluated"
    assert data["missing_information"] == []


def test_scan_reports_unreadable_fields_without_claiming_they_are_required(isolated_client):
    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        ocr_service=StubOCRService("")
    )
    try:
        response = isolated_client.post(
            "/api/documents/scan",
            data={"certificate_type": CertificateType.DOMICILE.value},
            files={"file": ("certificate.pdf", b"%PDF-1.7 sample", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_document_service, None)

    data = response.json()
    assert response.status_code == 200
    assert len(data["missing_information"]) == 4
    assert all(field["status"] == "not_detected" for field in data["fields"].values())
    assert data["requirement_check"]["status"] == "not_evaluated"


def test_scan_rejects_unsupported_categories_and_file_types(isolated_client):
    unsupported_category = isolated_client.post(
        "/api/documents/scan",
        data={"certificate_type": "marksheet"},
        files={"file": ("file.pdf", b"%PDF-1.7 sample", "application/pdf")},
    )
    unsupported_file = isolated_client.post(
        "/api/documents/scan",
        data={"certificate_type": CertificateType.CASTE.value},
        files={"file": ("file.txt", b"certificate", "text/plain")},
    )

    assert unsupported_category.status_code == 422
    assert unsupported_file.status_code == 415


def test_scan_endpoint_applies_rate_limit(isolated_client, monkeypatch):
    monkeypatch.setattr("app.routers.documents._SCAN_RATE_LIMIT", 0)

    response = isolated_client.post(
        "/api/documents/scan",
        data={"certificate_type": CertificateType.INCOME.value},
        files={"file": ("certificate.pdf", b"%PDF-1.7 sample", "application/pdf")},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"


@pytest.mark.parametrize("certificate_type", list(CertificateType))
def test_retrieval_returns_only_category_allowlisted_official_sources(certificate_type):
    references = retrieve_sources(certificate_type, "certificate requirements", limit=10)
    assert references
    assert all(
        reference["url"].startswith(
            (
                "https://aaplesarkar.mahaonline.gov.in/",
                "https://revenue.mahaonline.gov.in/",
                "https://cdnbbsr.s3waas.gov.in/",
            )
        )
        for reference in references
    )
    assert all(
        reference["verification_status"]
        and reference["retrieval_method"] == "local_sentence_transformer_cosine"
        and reference["retrieved_at"]
        and len(reference["source_sha256"]) == 64
        and reference["retrieved_passages"]
        for reference in references
    )

    if certificate_type is CertificateType.CASTE_VALIDITY:
        assert {reference["id"] for reference in references} == {
            "caste-act",
            "caste-validity-service",
        }
    if certificate_type is CertificateType.NATIONALITY:
        assert {reference["id"] for reference in references} == {
            "domicile-form",
            "domicile-service",
        }


def test_knowledge_manifest_fingerprints_only_curated_official_sources():
    manifest = source_manifest()

    assert len(manifest) == 8
    assert all(len(source["sha256"]) == 64 for source in manifest)
    assert all(source["chunk_count"] >= 0 for source in manifest)
    assert all(
        source["url"].startswith(
            (
                "https://aaplesarkar.mahaonline.gov.in/",
                "https://revenue.mahaonline.gov.in/",
                "https://cdnbbsr.s3waas.gov.in/",
            )
        )
        for source in manifest
    )


def test_caste_validity_retrieval_uses_only_its_exact_official_directory_row():
    references = retrieve_sources(
        CertificateType.CASTE_VALIDITY,
        "verification committee service",
        limit=10,
    )

    service_reference = next(
        reference
        for reference in references
        if reference["id"] == "caste-validity-service"
    )
    assert all(
        "Caste Certificate Verification Committee" in passage["text"]
        for passage in service_reference["retrieved_passages"]
    )


def test_duplicate_extracted_values_are_flagged_for_review():
    service = DocumentService(
        ocr_service=StubOCRService(
            "Certificate Number: MH-1234\nCertificate Number: MH-9876"
        )
    )
    result = service.scan_document(
        certificate_type=CertificateType.CASTE,
        filename="certificate.pdf",
        content_type="application/pdf",
        file_bytes=b"%PDF-1.7 sample",
    )

    assert result["possible_inconsistencies"][0]["field"] == "certificate_number"


def test_image_ocr_is_invoked_without_logging_or_persisting_document_text(monkeypatch):
    image = Image.new("RGB", (20, 20), color="white")
    image_bytes = BytesIO()
    image.save(image_bytes, format="PNG")
    monkeypatch.setattr("app.services.ocr_service.pytesseract.image_to_string", lambda *args, **kwargs: "readable")

    result = OCRService().extract_text(image_bytes.getvalue(), "image/png")

    assert result.text == "readable"
    assert result.method == "ocr"


def test_scanned_pdf_pages_are_rendered_and_sent_through_ocr(monkeypatch):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf_bytes = BytesIO()
    writer.write(pdf_bytes)
    monkeypatch.setattr("app.services.ocr_service.pytesseract.image_to_string", lambda *args, **kwargs: "scanned text")

    result = OCRService().extract_text(pdf_bytes.getvalue(), "application/pdf")

    assert result.text == "scanned text"
    assert result.method == "ocr"
    assert result.pages_processed == 1


def test_unavailable_ocr_is_reported_to_the_upload_client(isolated_client):
    class UnavailableOCRService:
        def extract_text(self, file_bytes: bytes, file_type: str) -> OCRResult:
            raise OCRUnavailableError("Tesseract OCR is not installed on the server.")

    app.dependency_overrides[get_document_service] = lambda: DocumentService(
        ocr_service=UnavailableOCRService()
    )
    try:
        response = isolated_client.post(
            "/api/documents/scan",
            data={"certificate_type": CertificateType.INCOME.value},
            files={"file": ("certificate.pdf", b"%PDF-1.7 sample", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_document_service, None)

    assert response.status_code == 503
    assert response.json()["detail"] == "Tesseract OCR is not installed on the server."
