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
from app.schemas.document import DynamicScholarshipDocumentsResponse
from app.schemas.recommendation import RecommendationMatch, RecommendationResponse
from app.schemas.scholarship_document import (
    ScholarshipDocumentResponse,
    ScholarshipDocumentUpdate,
    ScholarshipDocumentsResponse,
)
from app.services.document_vault_service import DocumentVaultService
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

    matching_service = MatchingService(db)
    matches = matching_service.recalculate_matches_for_student(student)

    scholarships_by_id = {
        s.id: s
        for s in db.query(Scholarship).filter(Scholarship.id.in_([m.scholarship_id for m in matches])).all()
    }
    recommendations = []
    for match in matches:
        scholarship = scholarships_by_id.get(match.scholarship_id)
        if scholarship is None:
            continue
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
                "doc_status": "not_started",
                "passed_rules": match.passed_rules or [],
                "failed_rules": match.failed_rules or [],
                "unknown_rules": match.unknown_rules or [],
                "warnings": match.warnings or [],
            }
        )

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
    if not matches:
        matches = MatchingService(db).recalculate_matches_for_student(student)
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

    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")


@router.get(
    "/recommendations/{student_id}/scholarship/{scholarship_id}/documents",
    response_model=DynamicScholarshipDocumentsResponse,
)
def get_scholarship_documents(
    student_id: str,
    scholarship_id: str,
    db: Session = Depends(get_db),
) -> DynamicScholarshipDocumentsResponse:
    _get_student_scholarship(student_id, scholarship_id, db)
    vault_service = DocumentVaultService(db)
    return vault_service.match_documents_for_scholarship(student_id, scholarship_id)


@router.post(
    "/recommendations/{student_id}/scholarship/{scholarship_id}/documents/match",
    response_model=DynamicScholarshipDocumentsResponse,
)
def match_scholarship_documents(
    student_id: str,
    scholarship_id: str,
    db: Session = Depends(get_db),
) -> DynamicScholarshipDocumentsResponse:
    _get_student_scholarship(student_id, scholarship_id, db)
    vault_service = DocumentVaultService(db)
    return vault_service.match_documents_for_scholarship(student_id, scholarship_id)


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
    if not document_name.strip():
        raise HTTPException(status_code=422, detail="Document name cannot be empty")

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


@router.get("/recommendations/{student_id}/scholarship/{scholarship_id}/eligibility")
def get_recommendation_eligibility(
    student_id: str,
    scholarship_id: str,
    db: Session = Depends(get_db),
):
    student = db.query(StudentProfile).filter(StudentProfile.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=404, detail="Student profile not found")
    scholarship = db.query(Scholarship).filter(Scholarship.id == scholarship_id).first()
    if scholarship is None:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    match = db.query(ScholarshipMatch).filter(
        ScholarshipMatch.student_id == student_id,
        ScholarshipMatch.scholarship_id == scholarship_id,
    ).first()

    if match:
        return {
            "student_id": student.id,
            "scholarship_id": scholarship.id,
            "scholarship_name": scholarship.scholarship_name,
            "match_status": match.match_status,
            "match_score": match.match_score,
            "passed_rules": match.passed_rules or [],
            "failed_rules": match.failed_rules or [],
            "unknown_rules": match.unknown_rules or [],
            "warnings": match.warnings or [],
        }

    result = evaluate_eligibility(student, scholarship)
    return {
        "student_id": student.id,
        "scholarship_id": scholarship.id,
        "scholarship_name": scholarship.scholarship_name,
        "match_status": result["match_status"],
        "match_score": result["match_score"],
        "passed_rules": result["passed_rules"],
        "failed_rules": result["failed_rules"],
        "unknown_rules": result["unknown_rules"],
        "warnings": result["warnings"],
    }
