from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.services.certificate_knowledge import (
    CertificateType,
    KnowledgeBaseUnavailableError,
)
from app.services.document_service import (
    DocumentService,
    MAX_UPLOAD_BYTES,
    UploadTooLargeError,
    UnsupportedMediaTypeError,
)
from app.services.ocr_service import InvalidDocumentError, OCRUnavailableError

router = APIRouter(prefix="/api", tags=["documents"])
_SCAN_REQUESTS: dict[str, deque[float]] = defaultdict(deque)
_SCAN_REQUESTS_LOCK = Lock()
_SCAN_RATE_LIMIT = 20
_SCAN_RATE_WINDOW_SECONDS = 60


def get_document_service() -> DocumentService:
    return DocumentService()


def enforce_scan_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    now = monotonic()
    with _SCAN_REQUESTS_LOCK:
        requests = _SCAN_REQUESTS[client_host]
        while requests and now - requests[0] >= _SCAN_RATE_WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= _SCAN_RATE_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Document scanning rate limit exceeded. Try again later.",
                headers={"Retry-After": str(_SCAN_RATE_WINDOW_SECONDS)},
            )
        requests.append(now)


@router.post("/documents/scan")
async def scan_document(
    certificate_type: CertificateType = Form(...),
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
    _: None = Depends(enforce_scan_rate_limit),
) -> dict:
    try:
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")

    try:
        return service.scan_document(
            certificate_type=certificate_type,
            filename=file.filename or "",
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )
    except UploadTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except UnsupportedMediaTypeError as error:
        raise HTTPException(status_code=415, detail=str(error)) from error
    except InvalidDocumentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OCRUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except KnowledgeBaseUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
