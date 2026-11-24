from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime
from sqlalchemy.sql import func
from database import Base


class Scholarship(Base):
    __tablename__ = "scholarships"

    id = Column(Integer, primary_key=True, index=True)
    scheme_name = Column(String(500), nullable=False)
    eligibility = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    tags = Column(Text, nullable=True)
    application_process = Column(Text, nullable=True)
    benefits = Column(Text, nullable=True)
    documents_required = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    department = Column(String(500), nullable=True)
    target_states = Column(Text, nullable=True)
    verification_status = Column(String(50), default="unverified")
    last_verified_at = Column(DateTime, nullable=True)


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    age = Column(Integer, nullable=True)
    gender = Column(String(50), nullable=True)
    state = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)
    family_income = Column(Float, nullable=True)
    qualification = Column(String(200), nullable=True)
    education_stage = Column(String(200), nullable=True)
    course = Column(String(200), nullable=True)
    stream = Column(String(200), nullable=True)
    percentage = Column(Float, nullable=True)
    disability = Column(String(50), nullable=True)
    minority = Column(String(50), nullable=True)
    sports = Column(String(50), nullable=True)
    exserviceman = Column(String(50), nullable=True)


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)

    email = Column(String, unique=True, index=True, nullable=False)

    password_hash = Column(String, nullable=False)

    age = Column(Integer, nullable=True)

    gender = Column(String, nullable=True)

    education_stage = Column(String, nullable=True)

    qualification = Column(String, nullable=True)

    course = Column(String, nullable=True)

    stream = Column(String, nullable=True)

    percentage = Column(Float, nullable=True)

    state = Column(String, nullable=True)

    category = Column(String, nullable=True)

    family_income = Column(Float, nullable=True)

    disability = Column(String, nullable=True)

    minority = Column(String, nullable=True)

    sports = Column(String, nullable=True)

    ex_serviceman = Column(String, nullable=True)

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )