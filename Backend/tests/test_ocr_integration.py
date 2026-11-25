from __future__ import annotations

import io
import shutil
import subprocess
from types import SimpleNamespace
from PIL import Image, ImageDraw
import pytest

from app.core.database import get_db
from app.main import app
from app.routers.health import (
    REQUIRED_OCR_LANGUAGES,
    check_ocr_health,
    resolve_tesseract_binary,
)
from app.services.ocr_service import OCRService, OCRUnavailableError


def create_test_image(text: str) -> bytes:
    """Generate a high-contrast RGB PNG containing test text for OCR testing."""
    image = Image.new("RGB", (400, 100), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 35), text, fill="black")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_health_reports_ocr_status(isolated_client):
    """Verify that /api/health exposes the OCR availability flag and diagnostics."""
    response = isolated_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert "ocr" in data
    assert data["ocr"] in {"available", "unavailable"}
    assert "diagnostics" in data
    assert "database" in data["diagnostics"]
    assert "ocr" in data["diagnostics"]
    assert data["status"] in {"ok", "degraded"}


def test_health_missing_tesseract(isolated_client, monkeypatch):
    """When Tesseract binary is not on PATH and no TESSERACT_CMD, OCR is reported unavailable and health degraded."""
    monkeypatch.delenv("TESSERACT_CMD", raising=False)
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    response = isolated_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ocr"] == "unavailable"
    assert data["diagnostics"]["ocr"]["status"] == "unavailable"
    assert "not found" in data["diagnostics"]["ocr"]["detail"].lower()


def test_health_invalid_executable_path(isolated_client, monkeypatch, tmp_path):
    """When TESSERACT_CMD is set to an invalid or non-existent path, report unavailable and degraded."""
    invalid_path = str(tmp_path / "nonexistent_tesseract.exe")
    monkeypatch.setenv("TESSERACT_CMD", invalid_path)
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    response = isolated_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ocr"] == "unavailable"
    assert data["diagnostics"]["ocr"]["status"] == "unavailable"


def test_health_missing_language_data(isolated_client, monkeypatch):
    """When Tesseract runs but mar or eng is missing from --list-langs, report unavailable and degraded."""
    monkeypatch.setattr("app.routers.health.resolve_tesseract_binary", lambda: "/usr/bin/tesseract")
    fake_proc = SimpleNamespace(
        returncode=0,
        stdout="List of available languages (2):\neng\nosd\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)

    response = isolated_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["ocr"] == "unavailable"
    assert data["diagnostics"]["ocr"]["status"] == "unavailable"
    assert "mar" in data["diagnostics"]["ocr"]["detail"]


def test_health_successful_ocr_availability(isolated_client, monkeypatch):
    """When DB is connected and Tesseract runs with both eng and mar, status is 'ok'."""
    monkeypatch.setattr("app.routers.health.resolve_tesseract_binary", lambda: "/usr/bin/tesseract")
    fake_proc = SimpleNamespace(
        returncode=0,
        stdout="List of available languages and other items (3):\neng\nmar\nosd\n",
        stderr="",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: fake_proc)

    response = isolated_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "connected"
    assert data["ocr"] == "available"
    assert data["diagnostics"]["ocr"]["status"] == "available"
    assert data["diagnostics"]["ocr"]["binary"] == "/usr/bin/tesseract"
    assert "eng" in data["diagnostics"]["ocr"]["languages"]
    assert "mar" in data["diagnostics"]["ocr"]["languages"]


def test_health_temporary_db_failure_still_returns_200(isolated_client):
    """A transient DB connection issue reports db unavailable and degraded without failing HTTP 200."""
    class FailingDB:
        def execute(self, *args, **kwargs):
            raise RuntimeError("Database connection timeout during cold start")

    app.dependency_overrides[get_db] = lambda: FailingDB()
    try:
        response = isolated_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["db"] == "unavailable"
        assert data["diagnostics"]["database"]["status"] == "unavailable"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_ocr_service_language_configuration():
    """Verify OCR service initializes with supported languages."""
    service = OCRService()
    assert "eng" in service.languages
    assert "mar" in service.languages


def test_ocr_service_execution_or_graceful_unavailable():
    """Verify that OCR extracts text when Tesseract is present, or raises OCRUnavailableError."""
    service = OCRService()
    image_bytes = create_test_image("Income Certificate 2026")
    has_tesseract = bool(shutil.which("tesseract"))

    if has_tesseract:
        result = service.extract_text(image_bytes, "image/png")
        assert result.method == "ocr"
        assert result.pages_processed == 1
        assert "Income" in result.text or "Certificate" in result.text
    else:
        with pytest.raises(OCRUnavailableError) as exc_info:
            service.extract_text(image_bytes, "image/png")
        assert "Tesseract OCR" in str(exc_info.value)


def test_resolve_tesseract_binary_prefers_valid_env(monkeypatch, tmp_path):
    """resolve_tesseract_binary respects valid executable TESSERACT_CMD."""
    fake_exe = tmp_path / "custom_tesseract.exe"
    fake_exe.write_text("binary content")
    monkeypatch.setenv("TESSERACT_CMD", str(fake_exe))
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    monkeypatch.setattr("os.access", lambda path, mode: True)

    assert resolve_tesseract_binary() == str(fake_exe)


def test_resolve_tesseract_binary_invalid_env_falls_back(monkeypatch):
    """resolve_tesseract_binary falls back to PATH when TESSERACT_CMD is non-existent."""
    monkeypatch.setenv("TESSERACT_CMD", "/nonexistent/tesseract")
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/tesseract" if cmd == "tesseract" else None)

    assert resolve_tesseract_binary() == "/usr/bin/tesseract"


def test_pdf_ocr_total_time_budget_enforced_before_ocr(monkeypatch):
    """When the 90-second PDF OCR budget is exhausted before OCR, raise OCRUnavailableError."""
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    pdf_bytes_buf = io.BytesIO()
    writer.write(pdf_bytes_buf)
    pdf_bytes = pdf_bytes_buf.getvalue()

    service = OCRService()
    # Mock monotonic such that after initialization it jumps past 90 seconds
    times = [0.0, 100.0, 100.0]
    monkeypatch.setattr("app.services.ocr_service.monotonic", lambda: times.pop(0) if times else 200.0)

    with pytest.raises(OCRUnavailableError) as exc:
        service.extract_text(pdf_bytes, "application/pdf")
    assert "90-second" in str(exc.value)

