from __future__ import annotations

import logging
import os
import shutil
import subprocess
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.ocr_service import resolve_tesseract_binary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["health"])

REQUIRED_OCR_LANGUAGES = ("eng", "mar")


def check_ocr_health() -> dict[str, Any]:
    """Verify that Tesseract is installed, executable, and contains required languages."""
    binary = resolve_tesseract_binary()
    if not binary:
        return {
            "status": "unavailable",
            "detail": "Tesseract binary not found or not executable",
            "languages": [],
        }

    try:
        proc = subprocess.run(
            [binary, "--list-langs"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3.0,
            check=False,
        )
        if proc.returncode != 0:
            error_msg = proc.stderr.strip() or f"process returned code {proc.returncode}"
            return {
                "status": "unavailable",
                "detail": f"Tesseract execution failed: {error_msg}",
                "languages": [],
            }

        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        available_languages = sorted(
            line for line in lines
            if not line.lower().startswith("list of available languages")
            and not line.endswith(":")
        )

        missing_languages = [
            lang for lang in REQUIRED_OCR_LANGUAGES
            if lang not in available_languages
        ]

        if missing_languages:
            return {
                "status": "unavailable",
                "detail": f"Missing required language data: {', '.join(missing_languages)}",
                "languages": available_languages,
            }

        return {
            "status": "available",
            "binary": binary,
            "languages": available_languages,
        }

    except (subprocess.SubprocessError, OSError, TimeoutError) as exc:
        return {
            "status": "unavailable",
            "detail": f"Error executing Tesseract: {exc}",
            "languages": [],
        }


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        db.execute(text("SELECT 1"))
        database_ok = True
    except Exception as exc:
        logger.warning("Database health check ping failed: %s", exc)
        database_ok = False

    ocr_info = check_ocr_health()
    ocr_ok = ocr_info.get("status") == "available"
    overall_status = "ok" if (database_ok and ocr_ok) else "degraded"

    return {
        "status": overall_status,
        "service": "scholarmate-api",
        "db": "connected" if database_ok else "unavailable",
        "ocr": ocr_info["status"],
        "diagnostics": {
            "database": {
                "status": "connected" if database_ok else "unavailable",
            },
            "ocr": ocr_info,
        },
    }
