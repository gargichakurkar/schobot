from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import Base, engine
from app.core.migrations import migrate_scholarship_columns
from app.models import (
    CounselorLink,
    Document,
    ReminderEvent,
    ReminderPreference,
    Scholarship,
    ScholarshipMatch,
    StudentProfile,
    StudentScholarshipDocument,
    StudentScholarshipProgress,
)  # noqa: F401
from app.routers.documents import router as documents_router
from app.routers.health import router as health_router
from app.routers.profiles import router as profiles_router
from app.routers.recommendations import router as recommendations_router
from app.routers.reminders import router as reminders_router
from app.routers.simulate import router as simulate_router
from app.routers.counselor import router as counselor_router
from app.routers.scholarships import router as scholarships_router
from app.routers.chat import router as chat_router

app = FastAPI(title=settings.app_name, version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(profiles_router)
app.include_router(scholarships_router)
app.include_router(recommendations_router)
app.include_router(simulate_router)
app.include_router(reminders_router)
app.include_router(counselor_router)
app.include_router(documents_router)
app.include_router(chat_router)

Base.metadata.create_all(bind=engine)
migrate_scholarship_columns(engine)


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "status": "online"}
