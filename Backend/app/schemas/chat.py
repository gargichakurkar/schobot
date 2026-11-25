from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    student_id: str | None = Field(default=None, min_length=1, max_length=36)
    message: str = Field(min_length=1, max_length=2000)
    conversation_history: list[HistoryMessage] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class ChatResponse(BaseModel):
    answer: str
    sources: list[dict] = Field(default_factory=list)
