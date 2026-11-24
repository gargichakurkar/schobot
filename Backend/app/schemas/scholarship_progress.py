from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ScholarshipProgressUpdate(BaseModel):
    doc_status: Literal["not_started", "in_progress", "verified"]
    notes: str | None = None


class ScholarshipProgressResponse(BaseModel):
    student_id: str
    scholarship_id: str
    doc_status: Literal["not_started", "in_progress", "verified"]
    notes: str | None = None
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
