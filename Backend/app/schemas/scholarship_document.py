from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


DocumentStatus = Literal["not_uploaded", "uploaded", "verified"]


class ScholarshipDocumentUpdate(BaseModel):
    status: DocumentStatus
    notes: str | None = None


class ScholarshipDocumentResponse(BaseModel):
    document_name: str
    status: DocumentStatus
    notes: str | None = None
    updated_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)


class ScholarshipDocumentsResponse(BaseModel):
    student_id: str
    scholarship_id: str
    documents: list[ScholarshipDocumentResponse]
