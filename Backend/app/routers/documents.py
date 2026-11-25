from __future__ import annotations

from collections import defaultdict, deque
from io import BytesIO
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.student_profile import StudentProfile
from app.schemas.document import (
    DocumentVerificationUpdate,
    VaultDocumentListResponse,
    VaultDocumentResponse,
)
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
from app.services.document_vault_service import DocumentVaultService
from app.services.ocr_service import InvalidDocumentError, OCRUnavailableError
from auth import decode_access_token, get_current_student, require_counselor_or_admin

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
    request: Request,
    certificate_type: CertificateType = Form(...),
    file: UploadFile = File(...),
    student_id: str | None = Form(None),
    save_to_vault: bool = Form(False),
    service: DocumentService = Depends(get_document_service),
    db: Session = Depends(get_db),
    _: None = Depends(enforce_scan_rate_limit),
) -> dict:
    try:
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB upload limit.")

    try:
        scan_result = service.scan_document(
            certificate_type=certificate_type,
            filename=file.filename or "",
            content_type=file.content_type or "",
            file_bytes=file_bytes,
        )

        saved_doc = None
        if save_to_vault:
            auth_header = request.headers.get("authorization")
            x_tok = request.headers.get("x-student-token")
            token = None
            if auth_header and auth_header.lower().startswith("bearer "):
                token = auth_header.split(" ", 1)[1].strip()
            elif x_tok:
                token = x_tok.strip()

            if not token:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required to save document to vault.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = decode_access_token(token)
            authed_student_id = payload.get("sub")
            if not authed_student_id:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid token: missing student identifier.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            if student_id and student_id != authed_student_id:
                raise HTTPException(
                    status_code=403,
                    detail="Forbidden: You cannot save documents to another student's vault.",
                )

            vault_service = DocumentVaultService(db)
            saved_doc = vault_service.upload_document(
                student_id=authed_student_id,
                document_type=certificate_type.value,
                filename=file.filename or "scanned_certificate.pdf",
                content_type=file.content_type or "application/octet-stream",
                file_bytes=file_bytes,
                run_ocr=False,  # OCR was already run during scan
            )
            scan_result["saved_to_vault"] = True
            scan_result["document_id"] = saved_doc.id
            scan_result["download_url"] = saved_doc.download_url
        else:
            scan_result["saved_to_vault"] = False

        return scan_result

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


# ---------------------------------------------------------
# Central Student Document Vault Endpoints
# ---------------------------------------------------------


@router.get("/student/documents", response_model=VaultDocumentListResponse)
def get_student_documents(
    student_id: str | None = None,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> VaultDocumentListResponse:
    if student_id and student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot access another student's documents.",
        )
    target_student_id = current_student.id
    vault = DocumentVaultService(db)
    documents = vault.get_student_documents(target_student_id)
    return VaultDocumentListResponse(
        student_id=target_student_id,
        documents=documents,
        total=len(documents),
    )


@router.post("/student/documents/upload", response_model=VaultDocumentResponse)
async def upload_student_document(
    document_type: str = Form(...),
    file: UploadFile = File(...),
    student_id: str | None = Form(None),
    run_ocr: bool = Form(True),
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> VaultDocumentResponse:
    if student_id and student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot upload documents to another student's vault.",
        )
    try:
        file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()

    vault = DocumentVaultService(db)
    return vault.upload_document(
        student_id=current_student.id,
        document_type=document_type,
        filename=file.filename or "document.pdf",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
        run_ocr=run_ocr,
    )


@router.get("/student/documents/{document_id}", response_model=VaultDocumentResponse)
def get_student_document(
    document_id: str,
    student_id: str | None = None,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> VaultDocumentResponse:
    if student_id and student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot access another student's documents.",
        )
    vault = DocumentVaultService(db)
    return vault.get_document(current_student.id, document_id)


@router.get("/student/documents/{document_id}/download")
def download_student_document(
    document_id: str,
    student_id: str | None = None,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if student_id and student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot access another student's documents.",
        )
    vault = DocumentVaultService(db)
    content, mime_type, filename = vault.download_document(current_student.id, document_id)
    return StreamingResponse(
        BytesIO(content),
        media_type=mime_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/student/documents/raw/{storage_path:path}")
def download_raw_storage_document(
    storage_path: str,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Raw storage download handler for local dev / testing."""
    if not storage_path.startswith(f"students/{current_student.id}/"):
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot access another student's stored file.",
        )
    vault = DocumentVaultService(db)
    try:
        content = vault.storage.download_file(storage_path)
        mime = "application/pdf" if storage_path.endswith(".pdf") else "image/png"
        return Response(content=content, media_type=mime)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/student/documents/{document_id}")
def delete_student_document(
    document_id: str,
    student_id: str | None = None,
    current_student: StudentProfile = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> dict:
    if student_id and student_id != current_student.id:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: You cannot modify or delete another student's documents.",
        )
    vault = DocumentVaultService(db)
    return vault.delete_document(current_student.id, document_id)


@router.patch("/counselor/documents/{document_id}/verify", response_model=VaultDocumentResponse)
def verify_document_endpoint(
    document_id: str,
    payload: DocumentVerificationUpdate,
    counselor: dict = Depends(require_counselor_or_admin),
    db: Session = Depends(get_db),
) -> VaultDocumentResponse:
    """Authorized endpoint for verification/rejection of student documents."""
    vault = DocumentVaultService(db)
    return vault.verify_document(
        document_id=document_id,
        verification_status=payload.verification_status,
        rejection_reason=payload.rejection_reason,
        reviewer_id=counselor.get("identifier") or "counselor",
    )
