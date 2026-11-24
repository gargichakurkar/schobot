
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from groq import Groq
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scholarship import Scholarship
from app.models.student_profile import StudentProfile


MIN_RELEVANCE_SCORE = 0.38
MAX_RETRIEVAL_RESULTS = 6
RESPONSE_LANGUAGE_DIRECTIVE = re.compile(r"^\[lang=(en|hi)\]\s*", re.IGNORECASE)
FIELD_WEIGHTS = {
    "scholarship_name": 4.0,
    "provider": 1.4,
    "state": 1.4,
    "category": 1.8,
    "qualification_text": 3.0,
    "description": 1.5,
    "benefits": 1.2,
    "required_documents": 0.8,
    "eligibility_details": 2.0,
    "eligible_level": 2.8,
    "eligible_course": 3.0,
    "gender_requirement": 1.2,
    "income_text": 1.0,
    "minimum_marks_text": 0.8,
}
STOP_WORDS = {
    "the", "and", "for", "are", "what", "which", "with", "from",
    "have", "do", "does", "how", "can", "you", "your", "about", "tell",
    "me", "is", "in", "of", "to", "a", "an", "my", "i", "please",
    "show", "find", "list", "some", "available", "information",
    "scholarship", "scholarships", "scheme", "schemes",
}


class AIChatService:
    def __init__(self, db: Session):
        self.db = db

        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not configured")

        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    @staticmethod
    def _normalized_tokens(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.casefold())
        normalized = []
        for word in words:
            if len(word) > 6 and word.endswith("ing"):
                word = word[:-3]
            elif len(word) > 4 and word.endswith("ies"):
                word = word[:-3] + "y"
            elif len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
                word = word[:-1]
            if word not in STOP_WORDS and (len(word) > 1 or word.isdigit()):
                normalized.append(word)
        return normalized

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return set(cls._normalized_tokens(text))

    @classmethod
    def _ordered_query_tokens(cls, text: str) -> list[str]:
        return cls._normalized_tokens(text)

    @staticmethod
    def _field_value(scholarship: Scholarship, field: str) -> str:
        value = getattr(scholarship, field, None)
        return str(value) if value else ""

    def _retrieve_scholarships(self, question: str) -> list[Scholarship]:
        query_tokens = self._ordered_query_tokens(question)
        if not query_tokens:
            return []

        scholarships = self.db.query(Scholarship).all()
        if not scholarships:
            return []

        query_token_set = set(query_tokens)
        query_phrase = " ".join(query_tokens)
        ranked: list[tuple[float, Scholarship]] = []
        exact_name_matches: list[tuple[float, Scholarship]] = []
        for scholarship in scholarships:
            token_weights = {token: 0.0 for token in query_token_set}
            for field, weight in FIELD_WEIGHTS.items():
                field_tokens = self._tokens(self._field_value(scholarship, field))
                for token in query_token_set & field_tokens:
                    token_weights[token] = max(token_weights[token], weight)

            matched_tokens = [token for token, weight in token_weights.items() if weight]
            if not matched_tokens:
                continue
            if len(query_token_set) >= 3 and len(matched_tokens) < 2:
                continue

            coverage = sum(
                min(token_weights[token], FIELD_WEIGHTS["scholarship_name"])
                for token in matched_tokens
            ) / (len(query_token_set) * FIELD_WEIGHTS["scholarship_name"])

            name_tokens = self._ordered_query_tokens(
                scholarship.scholarship_name or ""
            )
            name_phrase = " ".join(name_tokens)
            if name_phrase and (name_phrase in query_phrase or query_phrase in name_phrase):
                coverage = min(1.0, coverage + 0.2)
                exact_name_matches.append((coverage, scholarship))
            elif len(query_phrase) >= 8 and query_token_set.intersection(name_tokens):
                name_similarity = SequenceMatcher(
                    None,
                    query_phrase,
                    name_phrase,
                ).ratio()
                if name_similarity >= 0.72:
                    coverage = max(coverage, name_similarity * 0.65)

            if coverage >= MIN_RELEVANCE_SCORE:
                ranked.append((coverage, scholarship))

        if exact_name_matches:
            ranked = exact_name_matches
        ranked.sort(
            key=lambda item: (
                -item[0],
                (item[1].scholarship_name or "").casefold(),
                item[1].id or "",
            )
        )
        return [item[1] for item in ranked[:MAX_RETRIEVAL_RESULTS]]

    @staticmethod
    def _profile_context(student: StudentProfile | None) -> dict | None:
        if student is None:
            return None

        return {
            "education_level": student.education_level,
            "course": student.course,
            "study_year": student.study_year,
            "academic_score": student.academic_score,
            "score_type": student.score_type,
            "domicile_state": student.domicile_state,
            "study_state": student.study_state,
            "category": student.category,
            "gender": student.gender,
            "annual_family_income": student.annual_family_income,
            "has_disability_certificate": student.has_disability_certificate,
            "has_income_certificate": student.has_income_certificate,
        }

    @staticmethod
    def _application_status(value: str | None) -> str:
        normalized = (value or "").strip().casefold()
        if normalized in {"open", "closed", "unknown"}:
            return normalized
        return "unknown"

    def answer(self, question: str, student_id: str | None = None) -> dict:
        question = question.strip()
        language_match = RESPONSE_LANGUAGE_DIRECTIVE.match(question)
        response_language = (
            language_match.group(1).casefold() if language_match else None
        )
        if language_match:
            question = question[language_match.end() :].strip()

        if not question:
            raise ValueError("Question cannot be empty")

        student = None

        if student_id:
            student = (
                self.db.query(StudentProfile)
                .filter(StudentProfile.id == student_id)
                .first()
            )

            if student is None:
                raise ValueError("Student profile not found")

        scholarships = self._retrieve_scholarships(question)

        if not scholarships:
            if not self._tokens(question):
                return {
                    "answer": (
                        "I can help with scholarship information. Please narrow "
                        "your question with a scholarship name, field of study, "
                        "education level, state, or eligibility topic."
                    ),
                    "sources": [],
                }
            return {
                "answer": (
                    "I couldn't find relevant scholarship records in the "
                    "database for this question. Please try another question "
                    "or check whether scholarship data has been imported."
                ),
                "sources": [],
            }

        scholarship_context = []

        for item in scholarships:
            status = self._application_status(item.active_status)
            scholarship_context.append(
                {
                    "scholarship_id": item.id,
                    "name": item.scholarship_name,
                    "provider": item.provider,
                    "category": item.category,
                    "state": item.state,
                    "eligibility": item.eligibility_details,
                    "qualification": item.qualification_text,
                    "benefits": item.benefits,
                    "documents": item.required_documents,
                    "income_criteria": item.income_text,
                    "minimum_marks": item.minimum_marks_text,
                    "deadline": item.deadline.isoformat() if item.deadline else None,
                    "active_status": status,
                    "application_status": status,
                    "official_link": item.official_link,
                }
            )

        context = {
            "student_profile": self._profile_context(student),
            "scholarships": scholarship_context,
        }

        system_prompt = """
You are ScholarMate AI, a helpful scholarship information assistant.

Rules:
1. Use the supplied scholarship records as your source of truth.
2. Never invent scholarship names, deadlines, benefits, income limits,
   eligibility criteria, documents, or application links.
3. If the records do not contain an answer, clearly say that the
   information is unavailable in the current database.
4. You may explain scholarship information in simple language.
5. If a student profile is supplied, use relevant details to personalize
   explanations, but do not declare official eligibility yourself.
6. Eligibility decisions must be made by the application's deterministic
   eligibility rule engine, not by you.
7. Clearly distinguish confirmed information from information that
   needs verification.
8. Be concise, friendly, and helpful.
9. Respond in the language used by the student when possible.
10. Never assume a scholarship is currently accepting applications from its
    deadline, active_status, or internal database flag.
11. Treat active_status "unknown" as unknown and explicitly say its current
    application status needs verification from the official source.
12. Refer only to scholarship records included in the supplied context.
13. If the context lacks requested details, say those details are unavailable.
14. Keep scholarship names, official scheme names, and source URLs exactly as
    provided; do not translate or alter proper names or links.
"""

        language_instruction = (
            f"Response language preference: "
            f"{'Hindi' if response_language == 'hi' else 'English'}.\n\n"
            if response_language
            else ""
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"{language_instruction}"
                        f"Student question:\n{question}\n\n"
                        f"Available database context:\n"
                        f"{json.dumps(context, ensure_ascii=False, default=str)}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=800,
        )

        answer = response.choices[0].message.content or ""

        sources = [
            {
                "scholarship_id": item.id,
                "scholarship_name": item.scholarship_name,
                "official_link": item.official_link,
            }
            for item in scholarships
        ]

        return {
            "answer": answer,
            "sources": sources,
        }
