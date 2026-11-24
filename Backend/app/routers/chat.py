from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_chat_service import AIChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["AI Assistant"])


@router.post("", response_model=ChatResponse)
def chat_with_assistant(
    payload: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        service = AIChatService(db)
        result = service.answer(
            question=payload.message,
            student_id=payload.student_id,
        )
        return ChatResponse(**result)

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        logger.exception("AI chat request failed")
        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable. Please try again.",
        ) from exc
