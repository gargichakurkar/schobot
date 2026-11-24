# ============================================================
# SCHOBOT TRANSPARENT SCHOLARSHIP RANKING
# ============================================================

WEIGHTS = {
    "state": 20,
    "category": 15,
    "income": 20,
    "qualification": 15,
    "education_stage": 5,
    "course": 10,
    "stream": 5,
    "percentage": 5,
    "age": 2,
    "disability": 1,
    "minority": 1,
    "sports": 1,
    "exserviceman": 1
}


def calculate_match_score(eligibility_result):
    """
    Calculate a transparent scholarship match score.

    satisfied     -> earns the field weight
    not_satisfied -> earns 0
    unknown       -> does not earn points

    The denominator is always 100 so the score
    cannot become artificially high because of
    unknown fields.
    """

    conditions = eligibility_result.get(
        "conditions",
        {}
    )

    raw_score = 0

    satisfied_weight = 0
    known_weight = 0
    unknown_weight = 0

    for field, weight in WEIGHTS.items():

        result = conditions.get(field)

        if result == "satisfied":

            raw_score += weight
            satisfied_weight += weight
            known_weight += weight

        elif result == "not_satisfied":

            known_weight += weight

        elif result == "unknown":

            unknown_weight += weight

    # Fixed 100-point score
    match_percentage = round(
        raw_score,
        2
    )

    # How much of the scoring information
    # was actually known.
    coverage_percentage = round(
        known_weight,
        2
    )

    # Status
    status = eligibility_result.get(
        "status",
        "needs_verification"
    )

    return {
        "raw_score": raw_score,
        "match_percentage": match_percentage,
        "known_weight": known_weight,
        "unknown_weight": unknown_weight,
        "coverage_percentage": coverage_percentage,
        "status": status
    }


def rank_scholarships(
    scholarships,
    eligibility_results
):
    """
    Rank scholarships according to match score.

    Scholarships with an explicit not_satisfied
    condition are placed below scholarships that
    have no failed conditions.
    """

    ranked = []

    for scholarship in scholarships:

        result = eligibility_results.get(
            scholarship.id
        )

        if not result:
            continue

        score_data = calculate_match_score(
            result
        )

        # Number of failed conditions
        failed_count = len(
            result.get(
                "not_satisfied",
                []
            )
        )

        # Number of satisfied conditions
        satisfied_count = len(
            result.get(
                "satisfied",
                []
            )
        )

        ranked.append({

            "scholarship": scholarship,

            "match_score":
                score_data["raw_score"],

            "match_percentage":
                score_data["match_percentage"],

            "coverage_percentage":
                score_data["coverage_percentage"],

            "known_weight":
                score_data["known_weight"],

            "unknown_weight":
                score_data["unknown_weight"],

            "satisfied_count":
                satisfied_count,

            "failed_count":
                failed_count,

            "eligibility":
                result
        })

    # --------------------------------------------------------
    # SORTING
    # --------------------------------------------------------

    ranked.sort(
        key=lambda item: (
            item["eligibility"]["status"] == "eligible",
            item["failed_count"] == 0,
            item["match_percentage"],
            item["coverage_percentage"],
            item["satisfied_count"]
        ),
        reverse=True
    )

    return ranked