from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.scholarship import Scholarship
from app.models.scholarship_match import ScholarshipMatch
from app.models.student_scholarship_document import StudentScholarshipDocument
from app.models.student_profile import StudentProfile
from app.models.student_scholarship_progress import StudentScholarshipProgress
from app.schemas.recommendation import RecommendationMatch, RecommendationResponse
from app.schemas.scholarship_document import (
    ScholarshipDocumentResponse,
    ScholarshipDocumentUpdate,
    ScholarshipDocumentsResponse,
)
from app.schemas.scholarship_progress import ScholarshipProgressResponse, ScholarshipProgressUpdate
from app.schemas.student_profile import StudentProfileCreate, StudentProfileResponse
from app.services.matching_service import MatchingService
from app.services.profile_service import ProfileService
from app.services.ranking_service import sort_matches
from app.services.rule_engine import evaluate_eligibility
from app.services.best_bets_service import compute_best_bets
from app.utils.dedupe import dedupe_by_scholarship_id

router = APIRouter(prefix="/api", tags=["recommendations"])

REQUIRED_DOCUMENTS = (
    "Identity Proof (Aadhaar)",
    "Income Certificate",
    "Category Certificate",
    "Academic Marksheets",
    "Admission Proof",
    "Domicile Certificate",
    "Bank Passbook",
    "Passport-size Photograph",
)


@router.post("/profile/submit-and-recommend")
def submit_and_recommend(payload: StudentProfileCreate, db: Session = Depends(get_db)):
    service = ProfileService(db)
    student = service.create_profile(payload)

    scholarships = (
        db.query(Scholarship)
        .filter(
            Scholarship.scholarship_name != "Untitled Scholarship",
            or_(
                Scholarship.is_active.is_(True),
                Scholarship.active_status == "unknown",
            )
        )
        .all()
    )
    recommendations = []
    matches = []
    for scholarship in scholarships:
        result = evaluate_eligibility(student, scholarship)
        match = ScholarshipMatch(
            student_id=student.id,
            scholarship_id=scholarship.id,
            match_status=result["match_status"],
            match_score=result["match_score"],
            passed_rules=result["passed_rules"],
            failed_rules=result["failed_rules"],
            unknown_rules=result["unknown_rules"],
            warnings=result["warnings"],
        )
        matches.append(match)
        recommendations.append(
            {
                "scholarship_id": scholarship.id,
                "scholarship_name": scholarship.scholarship_name,
                "state": scholarship.state,
                "scholarship_type": scholarship.scholarship_type,
                "deadline": scholarship.deadline,
                "official_link": scholarship.official_link,
                "match_status": result["match_status"],
                "match_score": result["match_score"],
                "doc_status": "not_started",
                "passed_rules": result["passed_rules"],
                "failed_rules": result["failed_rules"],
                "unknown_rules": result["unknown_rules"],
                "warnings": result["warnings"],
            }
        )

    db.add_all(matches)
    db.commit()
    recommendations = dedupe_by_scholarship_id(sort_matches(recommendations))
    return {
        "student": StudentProfileResponse.model_validate(student),
        "recommendations": recommendations[:10],
        "best_bets": compute_best_bets(student, db),
    }


@router.get("/recommendations/{student_id}")
def get_recommendations(student_id: str, db: Session = Depends(get_db)):
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    matches = db.query(ScholarshipMatch).filter(ScholarshipMatch.student_id == student_id).all()
    progress_by_scholarship = {
        progress.scholarship_id: progress
        for progress in db.query(StudentScholarshipProgress)
        .filter(StudentScholarshipProgress.student_id == student_id)
        .all()
    }
    recommendations = []
    for match in matches:
        scholarship = db.query(Scholarship).filter(Scholarship.id == match.scholarship_id).first()
        if scholarship is None:
            continue
        progress = progress_by_scholarship.get(scholarship.id)
        recommendations.append(
            {
                "scholarship_id": scholarship.id,
                "scholarship_name": scholarship.scholarship_name,
                "state": scholarship.state,
                "scholarship_type": scholarship.scholarship_type,
                "deadline": scholarship.deadline,
                "official_link": scholarship.official_link,
                "match_status": match.match_status,
                "match_score": match.match_score,
                "doc_status": progress.doc_status if progress else "not_started",
                "notes": progress.notes if progress else None,
                "passed_rules": match.passed_rules or [],
                "failed_rules": match.failed_rules or [],
                "unknown_rules": match.unknown_rules or [],
                "warnings": match.warnings or [],
            }
        )
    return {
        "student": student,
        # Match status and rule evidence come directly from the backend match row.
        "recommendations": dedupe_by_scholarship_id(sort_matches(recommendations)),
        "best_bets": compute_best_bets(student, db),
    }


@router.patch(
    "/recommendations/{student_id}/scholarship/{scholarship_id}/progress",
    response_model=ScholarshipProgressResponse,
)
def update_scholarship_progress(
    student_id: str,
    scholarship_id: str,
    payload: ScholarshipProgressUpdate,
    db: Session = Depends(get_db),
) -> ScholarshipProgressResponse:
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")

    match = db.query(ScholarshipMatch).filter(
        ScholarshipMatch.student_id == student_id,
        ScholarshipMatch.scholarship_id == scholarship_id,
    ).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Scholarship recommendation not found for this student")

    progress = db.query(StudentScholarshipProgress).filter(
        StudentScholarshipProgress.student_id == student_id,
        StudentScholarshipProgress.scholarship_id == scholarship_id,
    ).first()
    if progress is None:
        progress = StudentScholarshipProgress(
            student_id=student_id,
            scholarship_id=scholarship_id,
            doc_status=payload.doc_status,
            notes=payload.notes,
        )
        db.add(progress)
    else:
        progress.doc_status = payload.doc_status
        progress.notes = payload.notes

    db.commit()
    db.refresh(progress)
    return ScholarshipProgressResponse.model_validate(progress)


def _get_student_scholarship(
    student_id: str,
    scholarship_id: str,
    db: Session,
) -> None:
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")

    match = db.query(ScholarshipMatch).filter(
        ScholarshipMatch.student_id == student_id,
        ScholarshipMatch.scholarship_id == scholarship_id,
    ).first()
    if match is None:
        raise HTTPException(status_code=404, detail="Scholarship recommendation not found for this student")


@router.get(
    "/recommendations/{student_id}/scholarship/{scholarship_id}/documents",
    response_model=ScholarshipDocumentsResponse,
)
def get_scholarship_documents(
    student_id: str,
    scholarship_id: str,
    db: Session = Depends(get_db),
) -> ScholarshipDocumentsResponse:
    _get_student_scholarship(student_id, scholarship_id, db)
    saved_documents = {
        document.document_name: document
        for document in db.query(StudentScholarshipDocument)
        .filter(
            StudentScholarshipDocument.student_id == student_id,
            StudentScholarshipDocument.scholarship_id == scholarship_id,
        )
        .all()
    }
    documents = [
        ScholarshipDocumentResponse(
            document_name=name,
            status=saved_documents[name].status if name in saved_documents else "not_uploaded",
            notes=saved_documents[name].notes if name in saved_documents else None,
            updated_at=saved_documents[name].updated_at if name in saved_documents else None,
        )
        for name in REQUIRED_DOCUMENTS
    ]
    return ScholarshipDocumentsResponse(
        student_id=student_id,
        scholarship_id=scholarship_id,
        documents=documents,
    )


@router.patch(
    "/recommendations/{student_id}/scholarship/{scholarship_id}/documents/{document_name}",
    response_model=ScholarshipDocumentResponse,
)
def update_scholarship_document(
    student_id: str,
    scholarship_id: str,
    document_name: str,
    payload: ScholarshipDocumentUpdate,
    db: Session = Depends(get_db),
) -> ScholarshipDocumentResponse:
    _get_student_scholarship(student_id, scholarship_id, db)
    if document_name not in REQUIRED_DOCUMENTS:
        raise HTTPException(status_code=404, detail="Required document not found")

    document = db.query(StudentScholarshipDocument).filter(
        StudentScholarshipDocument.student_id == student_id,
        StudentScholarshipDocument.scholarship_id == scholarship_id,
        StudentScholarshipDocument.document_name == document_name,
    ).first()
    if document is None:
        document = StudentScholarshipDocument(
            student_id=student_id,
            scholarship_id=scholarship_id,
            document_name=document_name,
            status=payload.status,
            notes=payload.notes,
        )
        db.add(document)
    else:
        document.status = payload.status
        if "notes" in payload.model_fields_set:
            document.notes = payload.notes

    db.commit()
    db.refresh(document)
    return ScholarshipDocumentResponse.model_validate(document)
