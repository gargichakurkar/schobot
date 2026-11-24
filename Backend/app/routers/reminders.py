from __future__ import annotations

from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.reminder_event import ReminderEvent
from app.models.reminder_preference import ReminderPreference
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile
from app.schemas.new_features import ReminderPreferenceRequest
from app.utils.eligibility_helpers import parse_date

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("/preferences")
def get_preferences(student_id: str, scholarship_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    query = db.query(ReminderPreference).filter(ReminderPreference.student_id == student_id)
    if scholarship_id:
        query = query.filter(ReminderPreference.scholarship_id == scholarship_id)
    return {"preferences": query.all()}


@router.post("/preferences")
def save_preference(payload: ReminderPreferenceRequest, db: Session = Depends(get_db)) -> dict:
    student = db.query(StudentProfile).filter(StudentProfile.id == payload.student_id).first()
    scholarship = db.query(Scholarship).filter(Scholarship.id == payload.scholarship_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    preference = db.query(ReminderPreference).filter(
        ReminderPreference.student_id == payload.student_id,
        ReminderPreference.scholarship_id == payload.scholarship_id,
    ).first()
    if preference is None:
        preference = ReminderPreference(
            student_id=payload.student_id,
            scholarship_id=payload.scholarship_id,
            channel=payload.channel,
            enabled=payload.enabled,
        )
        db.add(preference)
    else:
        preference.channel = payload.channel
        preference.enabled = payload.enabled

    if payload.enabled:
        event_dates: list[tuple[str, str, datetime]] = []
        deadline = parse_date(scholarship.deadline)
        if deadline:
            event_dates.append(("deadline", "Application deadline", datetime.combine(deadline, time.min, tzinfo=timezone.utc)))
        for index, milestone in enumerate(scholarship.milestones or []):
            milestone_date = parse_date(milestone.get("date") if isinstance(milestone, dict) else None)
            if milestone_date:
                label = str(milestone.get("label") or milestone.get("milestone_type") or f"Milestone {index + 1}")
                event_dates.append((f"milestone-{index}-{milestone_date.isoformat()}", label,
                                    datetime.combine(milestone_date, time.min, tzinfo=timezone.utc)))
        now = datetime.now(timezone.utc)
        for key, label, due_at in event_dates:
            if due_at < now:
                continue
            existing = db.query(ReminderEvent).filter(
                ReminderEvent.student_id == payload.student_id,
                ReminderEvent.scholarship_id == payload.scholarship_id,
                ReminderEvent.event_key == key,
            ).first()
            if existing is None:
                db.add(ReminderEvent(
                    student_id=payload.student_id,
                    scholarship_id=payload.scholarship_id,
                    event_key=key,
                    due_at=due_at,
                    message=f"{label}: {scholarship.scholarship_name}",
                ))

    db.commit()
    db.refresh(preference)
    return preference
