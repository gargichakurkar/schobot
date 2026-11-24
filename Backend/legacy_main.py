"""Legacy API entry point; the current API lives in app.main."""

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import Optional

from database import engine, Base, get_db
from models import Scholarship, StudentProfile
from schemas import (
    StudentProfileCreate,
    StudentProfileResponse,
    ScholarshipResponse
)
from eligibility import evaluate_scholarship
from ranking import rank_scholarships


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

Base.metadata.create_all(bind=engine)


# ============================================================
# FASTAPI APP
# ============================================================

app = FastAPI(
    title="Schobot API",
    description="Explainable AI Scholarship Recommendation and Verification System",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    return {
        "message": "Welcome to Schobot API",
        "status": "running",
        "version": "1.0.0"
    }


# ============================================================
# DATABASE STATUS
# ============================================================

@app.get("/database/status")
def database_status(
    db: Session = Depends(get_db)
):
    scholarship_count = (
        db.query(Scholarship).count()
    )

    student_count = (
        db.query(StudentProfile).count()
    )

    return {
        "database": "connected",
        "scholarships": scholarship_count,
        "students": student_count
    }


# ============================================================
# SCHOLARSHIP COUNT
# ============================================================

@app.get("/scholarships/count")
def scholarship_count(
    db: Session = Depends(get_db)
):
    count = db.query(Scholarship).count()

    return {
        "total_scholarships": count
    }


# ============================================================
# GET ALL SCHOLARSHIPS
# ============================================================

@app.get(
    "/scholarships",
    response_model=list[ScholarshipResponse]
)
def get_scholarships(
    skip: int = 0,
    limit: int = Query(
        50,
        ge=1,
        le=200
    ),
    db: Session = Depends(get_db)
):

    scholarships = (
        db.query(Scholarship)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return scholarships


# ============================================================
# SEARCH SCHOLARSHIPS
#
# IMPORTANT:
# This route MUST come BEFORE
# /scholarships/{scholarship_id}
# ============================================================

@app.get("/scholarships/search")
def search_scholarships(
    query: Optional[str] = None,
    state: Optional[str] = None,
    category: Optional[str] = None,
    qualification: Optional[str] = None,
    db: Session = Depends(get_db)
):

    scholarships = (
        db.query(Scholarship)
        .all()
    )

    results = []


    for scholarship in scholarships:

        # ----------------------------------------------------
        # CREATE SEARCHABLE TEXT
        # ----------------------------------------------------

        searchable_text = " ".join(
            filter(
                None,
                [
                    scholarship.scheme_name,
                    scholarship.eligibility,
                    scholarship.details,
                    scholarship.tags,
                    scholarship.application_process,
                    scholarship.benefits,
                    scholarship.documents_required,
                    scholarship.department,
                    scholarship.target_states
                ]
            )
        ).lower()


        # ----------------------------------------------------
        # GENERAL SEARCH
        # ----------------------------------------------------

        if query:

            query_text = (
                query.strip().lower()
            )

            if query_text not in searchable_text:
                continue


        # ----------------------------------------------------
        # STATE FILTER
        # ----------------------------------------------------

        if state:

            state_text = " ".join(
                filter(
                    None,
                    [
                        scholarship.target_states,
                        scholarship.eligibility,
                        scholarship.details
                    ]
                )
            ).lower()

            if (
                state.strip().lower()
                not in state_text
            ):
                continue


        # ----------------------------------------------------
        # CATEGORY FILTER
        # ----------------------------------------------------

        if category:

            category_text = " ".join(
                filter(
                    None,
                    [
                        scholarship.eligibility,
                        scholarship.details,
                        scholarship.tags
                    ]
                )
            ).lower()

            if (
                category.strip().lower()
                not in category_text
            ):
                continue


        # ----------------------------------------------------
        # QUALIFICATION FILTER
        # ----------------------------------------------------

        if qualification:

            qualification_text = " ".join(
                filter(
                    None,
                    [
                        scholarship.eligibility,
                        scholarship.details,
                        scholarship.tags
                    ]
                )
            ).lower()

            if (
                qualification.strip().lower()
                not in qualification_text
            ):
                continue


        results.append(scholarship)


    return {
        "total_matches": len(results),
        "scholarships": results[:100]
    }


# ============================================================
# GET SINGLE SCHOLARSHIP
#
# Keep this AFTER /scholarships/search
# ============================================================

@app.get(
    "/scholarships/{scholarship_id}",
    response_model=ScholarshipResponse
)
def get_scholarship(
    scholarship_id: int,
    db: Session = Depends(get_db)
):

    scholarship = (
        db.query(Scholarship)
        .filter(
            Scholarship.id == scholarship_id
        )
        .first()
    )

    if not scholarship:

        raise HTTPException(
            status_code=404,
            detail="Scholarship not found"
        )

    return scholarship


# ============================================================
# CREATE STUDENT PROFILE
# ============================================================

@app.post(
    "/student/profile",
    response_model=StudentProfileResponse
)
def create_student_profile(
    student: StudentProfileCreate,
    db: Session = Depends(get_db)
):

    profile = StudentProfile(
        **student.model_dump()
    )

    db.add(profile)

    db.commit()

    db.refresh(profile)

    return profile


# ============================================================
# GET STUDENT PROFILE
# ============================================================

@app.get(
    "/student/profile/{profile_id}",
    response_model=StudentProfileResponse
)
def get_student_profile(
    profile_id: int,
    db: Session = Depends(get_db)
):

    profile = (
        db.query(StudentProfile)
        .filter(
            StudentProfile.id == profile_id
        )
        .first()
    )

    if not profile:

        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    return profile


# ============================================================
# CHECK ELIGIBILITY
# ============================================================

@app.get(
    "/eligibility/{profile_id}"
)
def check_eligibility(
    profile_id: int,
    db: Session = Depends(get_db)
):

    student = (
        db.query(StudentProfile)
        .filter(
            StudentProfile.id == profile_id
        )
        .first()
    )

    if not student:

        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )


    scholarships = (
        db.query(Scholarship)
        .all()
    )

    eligible = []


    for scholarship in scholarships:

        result = evaluate_scholarship(
            student,
            scholarship
        )

        if result["status"] in [
            "eligible",
            "needs_verification"
        ]:

            eligible.append(
                {
                    "scholarship": scholarship,
                    "eligibility": result
                }
            )


    return {
        "student_profile": student,
        "total_eligible": len(eligible),
        "scholarships": eligible
    }


# ============================================================
# RECOMMENDED SCHOLARSHIPS
# ============================================================

@app.get(
    "/scholarships/recommended/{profile_id}"
)
def recommended_scholarships(
    profile_id: int,
    db: Session = Depends(get_db)
):

    student = (
        db.query(StudentProfile)
        .filter(
            StudentProfile.id == profile_id
        )
        .first()
    )

    if not student:

        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )


    scholarships = (
        db.query(Scholarship)
        .all()
    )


    eligibility_results = {}


    for scholarship in scholarships:

        result = evaluate_scholarship(
            student,
            scholarship
        )

        eligibility_results[
            scholarship.id
        ] = result


    ranked = rank_scholarships(
        scholarships,
        eligibility_results
    )


    recommendations = []


    for item in ranked[:50]:

        recommendations.append(
            {
                "scholarship": item["scholarship"],

                "match_score":
                    item["match_score"],

                "match_percentage":
                    item.get(
                        "match_percentage",
                        item["match_score"]
                    ),

                "coverage_percentage":
                    item.get(
                        "coverage_percentage",
                        0
                    ),

                "known_weight":
                    item.get(
                        "known_weight",
                        0
                    ),

                "unknown_weight":
                    item.get(
                        "unknown_weight",
                        0
                    ),

                "satisfied_count":
                    item.get(
                        "satisfied_count",
                        0
                    ),

                "failed_count":
                    item.get(
                        "failed_count",
                        0
                    ),

                "eligibility":
                    item["eligibility"]
            }
        )


    return {
        "student_profile": student,
        "total_recommendations":
            len(recommendations),
        "recommendations":
            recommendations
    }


# ============================================================
# SCHOLARSHIP EXPLANATION
# ============================================================

@app.get(
    "/scholarships/{scholarship_id}/explanation/{profile_id}"
)
def scholarship_explanation(
    scholarship_id: int,
    profile_id: int,
    db: Session = Depends(get_db)
):

    # --------------------------------------------------------
    # FIND STUDENT
    # --------------------------------------------------------

    student = (
        db.query(StudentProfile)
        .filter(
            StudentProfile.id == profile_id
        )
        .first()
    )

    if not student:

        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )


    # --------------------------------------------------------
    # FIND SCHOLARSHIP
    # --------------------------------------------------------

    scholarship = (
        db.query(Scholarship)
        .filter(
            Scholarship.id == scholarship_id
        )
        .first()
    )

    if not scholarship:

        raise HTTPException(
            status_code=404,
            detail="Scholarship not found"
        )


    # --------------------------------------------------------
    # EVALUATE
    # --------------------------------------------------------

    result = evaluate_scholarship(
        student,
        scholarship
    )


    # --------------------------------------------------------
    # HUMAN READABLE EXPLANATIONS
    # --------------------------------------------------------

    explanations = {

        "age": {

            "satisfied":
                "Your age satisfies the age requirement identified in the scholarship information.",

            "not_satisfied":
                "Your age does not satisfy the age requirement identified in the scholarship information.",

            "unknown":
                "A clear age requirement could not be identified."
        },


        "state": {

            "satisfied":
                "Your state matches the scholarship's available state criteria.",

            "not_satisfied":
                "Your state does not match the scholarship's stated state criteria.",

            "unknown":
                "The scholarship does not provide enough clear information about state eligibility."
        },


        "category": {

            "satisfied":
                "Your category appears in the scholarship eligibility criteria.",

            "not_satisfied":
                "Your category does not match the stated category criteria.",

            "unknown":
                "The scholarship does not provide enough clear information about category eligibility."
        },


        "income": {

            "satisfied":
                "Your family income is within the income limit identified in the scholarship information.",

            "not_satisfied":
                "Your family income is above the income limit identified in the scholarship information.",

            "unknown":
                "A clear income limit could not be identified from the scholarship information."
        },


        "qualification": {

            "satisfied":
                "Your qualification matches the scholarship's stated qualification requirements.",

            "not_satisfied":
                "Your qualification does not match the stated qualification requirements.",

            "unknown":
                "The scholarship information does not clearly specify a qualification requirement."
        },


        "education_stage": {

            "satisfied":
                "Your education stage appears to match the scholarship requirements.",

            "not_satisfied":
                "Your education stage does not match the stated scholarship requirements.",

            "unknown":
                "The scholarship information does not clearly specify an education stage."
        },


        "course": {

            "satisfied":
                "Your course appears to match the scholarship information.",

            "not_satisfied":
                "Your course does not appear to match the scholarship information.",

            "unknown":
                "The scholarship information does not clearly specify whether your course is eligible."
        },


        "stream": {

            "satisfied":
                "Your academic stream appears to match the scholarship requirements.",

            "not_satisfied":
                "Your academic stream does not appear to match the scholarship requirements.",

            "unknown":
                "The scholarship information does not clearly specify an academic stream."
        },


        "percentage": {

            "satisfied":
                "Your percentage meets the minimum percentage identified in the scholarship information.",

            "not_satisfied":
                "Your percentage does not meet the minimum percentage identified in the scholarship information.",

            "unknown":
                "A clear minimum percentage requirement could not be identified."
        },


        "disability": {

            "satisfied":
                "Your disability information does not conflict with the available scholarship criteria.",

            "not_satisfied":
                "Your disability information does not match the stated scholarship criteria.",

            "unknown":
                "The scholarship information does not clearly specify how disability status affects eligibility."
        },


        "minority": {

            "satisfied":
                "Your minority information does not conflict with the available scholarship criteria.",

            "not_satisfied":
                "Your minority information does not match the stated scholarship criteria.",

            "unknown":
                "The scholarship information does not clearly specify minority eligibility."
        },


        "sports": {

            "satisfied":
                "Your sports information does not conflict with the available scholarship criteria.",

            "not_satisfied":
                "Your sports information does not match the stated scholarship criteria.",

            "unknown":
                "The scholarship information does not clearly specify sports eligibility."
        },


        "exserviceman": {

            "satisfied":
                "Your ex-serviceman information does not conflict with the available scholarship criteria.",

            "not_satisfied":
                "Your ex-serviceman information does not match the stated scholarship criteria.",

            "unknown":
                "The scholarship information does not clearly specify ex-serviceman eligibility."
        }
    }


    # --------------------------------------------------------
    # BUILD EXPLANATION
    # --------------------------------------------------------

    reasons = []
    warnings = []
    missing_information = []


    for field, status in result[
        "conditions"
    ].items():

        message = explanations.get(
            field,
            {}
        ).get(
            status,
            "Eligibility information could not be determined."
        )


        if status == "satisfied":

            reasons.append(
                {
                    "field": field,
                    "message": message
                }
            )


        elif status == "not_satisfied":

            warnings.append(
                {
                    "field": field,
                    "message": message
                }
            )


        elif status == "unknown":

            missing_information.append(
                {
                    "field": field,
                    "message": message
                }
            )


    return {

        "scholarship_id":
            scholarship.id,

        "scholarship_name":
            scholarship.scheme_name,

        "student_name":
            student.name,

        "status":
            result["status"],

        "summary": {

            "matched_conditions":
                len(result["satisfied"]),

            "failed_conditions":
                len(result["not_satisfied"]),

            "unknown_conditions":
                len(result["unknown"])
        },

        "reasons":
            reasons,

        "warnings":
            warnings,

        "missing_information":
            missing_information,

        "conditions":
            result["conditions"],

        "source_url":
            scholarship.source_url
    }
