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
        is_active=False,
        active_status="unknown",
        **values,
    )
    db_session.add(scholarship)
    db_session.commit()
    return scholarship


def make_service(db_session) -> AIChatService:
    service = AIChatService.__new__(AIChatService)
    service.db = db_session
    return service


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
