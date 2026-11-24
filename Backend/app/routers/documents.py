from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/documents")
def placeholder_documents():
    return {"status": "not_implemented", "message": "OCR document intake is planned for a later phase."}
