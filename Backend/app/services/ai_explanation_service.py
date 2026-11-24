from __future__ import annotations


class AIExplanationService:
    """This service is intentionally passive in MVP. It explains results without changing eligibility."""

    def explain_rules(self, result: dict) -> dict:
        return {
            "summary": "Eligibility was determined by the deterministic rule engine.",
            "result": result,
        }
