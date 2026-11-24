from __future__ import annotations

from pydantic import BaseModel


class DocumentBase(BaseModel):
    student_id: str | None = None
    document_type: str | None = None
    file_name: str | None = None
    extracted_text: str | None = None


class DocumentResponse(DocumentBase):
    id: str
