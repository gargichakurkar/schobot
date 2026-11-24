from __future__ import annotations


def sort_matches(matches: list[dict]) -> list[dict]:
    def status_rank(status: str) -> int:
        ordering = {"likely_eligible": 0, "needs_verification": 1, "not_matched": 2, "expired": 3}
        return ordering.get(status, 99)

    return sorted(
        matches,
        key=lambda item: (
            status_rank(item.get("match_status", "not_matched")),
            -float(item.get("match_score", 0)),
        ),
    )
