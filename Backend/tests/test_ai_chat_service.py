from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import Scholarship
from app.models.scholarship_match import ScholarshipMatch
from app.models.student_profile import StudentProfile
from app.services.ai_chat_service import AIChatService


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def add_scholarship(db_session, name: str, **values) -> Scholarship:
    scholarship = Scholarship(
        scholarship_name=name,
        provider=values.pop("provider", "Government of India"),
        is_active=values.pop("is_active", False),
        active_status=values.pop("active_status", "unknown"),
        **values,
    )
    db_session.add(scholarship)
    db_session.commit()
    return scholarship


def add_student(db_session, **values) -> StudentProfile:
    student_values = {
        "full_name": "Asha Verma",
        "education_level": "Undergraduate",
        "course": "B.Tech",
        "study_year": "2nd Year",
        "academic_score": 88,
        "score_type": "Percentage",
        "domicile_state": "Maharashtra",
        "study_state": "Maharashtra",
        "category": "General",
        "gender": "Female",
        "annual_family_income": 150000,
    }
    student_values.update(values)
    student = StudentProfile(**student_values)
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student


def test_missing_disability_certificate_stays_unknown_on_new_profile(db_session):
    student = add_student(db_session)

    assert student.has_disability_certificate is None


def make_service(db_session) -> AIChatService:
    service = AIChatService.__new__(AIChatService)
    service.db = db_session
    return service


def configure_fake_completion(service: AIChatService):
    class FakeCompletions:
        request = None

        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="Eligibility details are shown.")
                    )
                ]
            )

    completions = FakeCompletions()
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.model = "test-model"
    return completions


def add_eligible_scholarship(db_session, **overrides) -> Scholarship:
    values = {
        "state": "All India",
        "category": "General",
        "eligible_level": "Undergraduate",
        "qualification_text": "Undergraduate students",
        "eligible_course": "B.Tech",
        "min_percentage": 75,
        "max_income": 250000,
        "deadline": datetime(2035, 3, 31, tzinfo=timezone.utc),
        "is_active": True,
        "active_status": "open",
        "official_link": "https://scholarships.gov.in/apply",
        "required_documents": "Documents: Income Certificate; Academic Marksheets",
    }
    values.update(overrides)
    return add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        **values,
    )


def test_query_tokenization_removes_generic_terms_and_normalizes_plurals():
    assert AIChatService._tokens(
        "Pragati Scholarship Scheme for Girl Students"
    ) == {"pragati", "girl", "student"}
    assert AIChatService._tokens("What scholarships do you have?") == set()


def test_retrieval_includes_inactive_records_and_ranks_specific_and_engineering_queries(
    db_session,
):
    specific = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
    )
    add_scholarship(db_session, "Pragati Merit Grant")
    engineering = add_scholarship(
        db_session,
        "National Technical Scholarship",
        eligible_course="Engineering",
        qualification_text="Undergraduate engineering students",
    )
    add_scholarship(
        db_session,
        "Medical Achievement Grant",
        eligible_course="Medicine",
    )
    service = make_service(db_session)

    pragati_results = service._retrieve_scholarships("Pragati Scholarship")
    specific_results = service._retrieve_scholarships(
        "Pragati Scholarship Scheme for Girl Students"
    )
    engineering_results = service._retrieve_scholarships("engineering scholarships")

    assert specific in pragati_results
    assert specific_results == [specific]
    assert all(item.is_active is False for item in pragati_results + specific_results)
    assert [item.id for item in engineering_results] == [engineering.id]
    assert all(item.scholarship_name != "Medical Achievement Grant" for item in engineering_results)


def test_answer_context_and_sources_use_only_retrieved_records_and_status_is_unknown(
    db_session,
):
    requested = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        official_link="https://scholarships.gov.in/apply",
        deadline=datetime(2027, 3, 31, tzinfo=timezone.utc),
        benefits="Annual tuition assistance",
    )
    add_scholarship(db_session, "Unrelated Medical Grant")

    class FakeCompletions:
        request = None

        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="The listed grant provides tuition assistance.")
                    )
                ]
            )

    completions = FakeCompletions()
    service = make_service(db_session)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.model = "test-model"

    response = service.answer("Pragati Scholarship Scheme for Girl Students")

    assert response["sources"] == [
        {
            "scholarship_id": requested.id,
            "scholarship_name": requested.scholarship_name,
            "official_link": requested.official_link,
        }
    ]
    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert len(context["scholarships"]) == 1
    assert context["scholarships"][0]["active_status"] == "unknown"
    assert context["scholarships"][0]["application_status"] == "unknown"
    assert context["scholarships"][0]["deadline"] == requested.deadline.isoformat()
    assert context["scholarships"][0]["official_link"] == requested.official_link


def test_language_directive_preserves_question_retrieval_and_prompts_hindi(
    db_session,
):
    requested = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        official_link="https://scholarships.gov.in/apply",
    )

    class FakeCompletions:
        request = None

        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="उत्तर उपलब्ध है।")
                    )
                ]
            )

    completions = FakeCompletions()
    service = make_service(db_session)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.model = "test-model"

    response = service.answer(
        "[lang=hi] Pragati Scholarship Scheme for Girl Students"
    )

    assert response["sources"][0]["scholarship_id"] == requested.id
    user_message = completions.request["messages"][1]["content"]
    assert user_message.startswith("Response language preference: Hindi.")
    assert (
        "Student question:\nPragati Scholarship Scheme for Girl Students"
        in user_message
    )
    assert "Response language preference: Hindi." in user_message
    assert "do not translate or alter proper names or links" in completions.request[
        "messages"
    ][0]["content"]


def test_broad_question_with_no_discriminative_terms_asks_for_clarification(
    db_session,
):
    add_scholarship(db_session, "Pragati Scholarship Scheme for Girl Students")
    service = make_service(db_session)
    service.client = SimpleNamespace()

    response = service.answer("What scholarships do you have?")

    assert response["sources"] == []
    assert "narrow your question" in response["answer"]


def test_personalized_eligibility_question_includes_rule_engine_results(db_session):
    student = add_student(db_session)
    scholarship = add_eligible_scholarship(db_session)
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    response = service.answer(
        "Am I eligible for Pragati Scholarship?",
        student_id=student.id,
    )

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert response["sources"][0]["scholarship_id"] == scholarship.id
    assert len(context["eligibility_results"]) == 1
    result = context["eligibility_results"][0]
    assert result["scholarship_name"] == scholarship.scholarship_name
    assert result["official_link"] == scholarship.official_link
    assert result["match_status"] == "likely_eligible"
    assert result["match_score"] > 0
    assert result["passed_rules"]
    assert result["failed_rules"] == []
    assert result["unknown_rules"] == []
    assert result["warnings"] == []


def test_why_am_i_eligible_recomputes_candidate_instead_of_trusting_saved_match(
    db_session,
):
    student = add_student(db_session)
    scholarship = add_eligible_scholarship(db_session)
    db_session.add(
        ScholarshipMatch(
            student_id=student.id,
            scholarship_id=scholarship.id,
            match_status="not_matched",
            match_score=1,
        )
    )
    db_session.commit()
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    service.answer("Why am I eligible?", student_id=student.id)

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert context["eligibility_results"][0]["match_status"] == "likely_eligible"
    assert db_session.query(ScholarshipMatch).count() == 1


def test_why_am_i_not_eligible_explains_failed_engine_rules(db_session):
    student = add_student(db_session, category="SC")
    scholarship = add_eligible_scholarship(db_session)
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    service.answer(
        "Why am I not eligible for Pragati Scholarship?",
        student_id=student.id,
    )

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    result = context["eligibility_results"][0]
    assert result["match_status"] == "not_matched"
    assert any(rule["field"] == "category" for rule in result["failed_rules"])


def test_missing_profile_requests_profile_before_personalizing(db_session):
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    response = service.answer(
        "Am I eligible for Pragati Scholarship?",
        student_id="00000000-0000-4000-8000-000000000001",
    )

    assert "complete and save your student profile" in response["answer"]
    assert response["sources"] == []
    assert completions.request is None


def test_eligibility_question_with_no_relevant_scholarships_returns_no_match_message(
    db_session,
):
    student = add_student(db_session)
    service = make_service(db_session)
    service.client = SimpleNamespace()

    response = service.answer(
        "Am I eligible for the Unlisted Opportunity?",
        student_id=student.id,
    )

    assert response["sources"] == []
    assert "couldn't find relevant scholarship records" in response["answer"]


def test_generic_scholarship_question_without_student_id_stays_general(db_session):
    scholarship = add_eligible_scholarship(db_session)
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    response = service.answer("Tell me about Pragati Scholarship")

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert response["sources"][0]["scholarship_id"] == scholarship.id
    assert context["student_profile"] is None
    assert "eligibility_results" not in context


def test_chat_does_not_create_scholarship_match_rows(db_session):
    student = add_student(db_session)
    add_eligible_scholarship(db_session)
    service = make_service(db_session)
    configure_fake_completion(service)

    assert db_session.query(ScholarshipMatch).count() == 0
    service.answer(
        "Am I eligible for Pragati Scholarship?",
        student_id=student.id,
    )
    assert db_session.query(ScholarshipMatch).count() == 0


def test_documents_question_includes_required_documents(db_session):
    scholarship = add_eligible_scholarship(db_session)
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    service.answer("What documents do I need for Pragati Scholarship?")

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert context["scholarships"][0]["documents"] == scholarship.required_documents


def test_generic_documents_question_uses_existing_student_recommendations(db_session):
    student = add_student(db_session)
    scholarship = add_eligible_scholarship(db_session)
    db_session.add(
        ScholarshipMatch(
            student_id=student.id,
            scholarship_id=scholarship.id,
            match_status="likely_eligible",
            match_score=95,
        )
    )
    db_session.commit()
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    service.answer("What documents do I need?", student_id=student.id)

    user_message = completions.request["messages"][1]["content"]
    context = json.loads(user_message.split("Available database context:\n", 1)[1])
    assert context["scholarships"][0]["documents"] == scholarship.required_documents
    assert db_session.query(ScholarshipMatch).count() == 1


def test_language_directive_prompts_marathi(db_session):
    requested = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        official_link="https://scholarships.gov.in/apply",
    )

    class FakeCompletions:
        request = None

        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="माहिती उपलब्ध आहे.")
                    )
                ]
            )

    completions = FakeCompletions()
    service = make_service(db_session)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    service.model = "test-model"

    response = service.answer(
        "[lang=mr] Pragati Scholarship Scheme for Girl Students"
    )

    assert response["sources"][0]["scholarship_id"] == requested.id
    user_message = completions.request["messages"][1]["content"]
    assert user_message.startswith("Response language preference: Marathi.")


def test_conversation_history_resolves_followup_scholarship_reference(db_session):
    requested = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        official_link="https://scholarships.gov.in/apply",
        deadline=datetime(2027, 3, 31, tzinfo=timezone.utc),
    )
    service = make_service(db_session)
    completions = configure_fake_completion(service)

    history = [
        {"role": "user", "content": "Tell me about Pragati Scholarship Scheme for Girl Students"},
        {"role": "assistant", "content": "Pragati scholarship provides assistance for girl students."},
    ]

    response = service.answer(
        "What is its deadline?",
        conversation_history=history,
    )

    assert len(response["sources"]) >= 1
    assert response["sources"][0]["scholarship_id"] == requested.id
    messages = completions.request["messages"]
    # Check that history was passed to completions
    assert any(m.get("content") == history[0]["content"] for m in messages)


def test_groq_failure_returns_grounded_fallback_from_database(db_session):
    requested = add_scholarship(
        db_session,
        "Pragati Scholarship Scheme for Girl Students",
        official_link="https://scholarships.gov.in/apply",
        benefits="Rs. 50,000 per annum",
    )

    class FailingCompletions:
        def create(self, **kwargs):
            raise RuntimeError("Groq API rate limit or network error")

    service = make_service(db_session)
    service.client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletions()))
    service.model = "test-model"

    response = service.answer("Tell me about Pragati Scholarship Scheme for Girl Students")

    assert response["sources"][0]["scholarship_id"] == requested.id
    assert "Here is verified information from our scholarship database" in response["answer"]
    assert requested.scholarship_name in response["answer"]
    assert requested.official_link in response["answer"]
