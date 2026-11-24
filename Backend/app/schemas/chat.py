from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    student_id: str | None = Field(default=None, min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=2000)

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] = Field(default_factory=list)
