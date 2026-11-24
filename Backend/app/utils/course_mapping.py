from __future__ import annotations

COURSE_ALIASES = {
    "btech": "B.Tech",
    "b.tech": "B.Tech",
    "be": "B.E",
    "b.e": "B.E",
    "bsc": "B.Sc",
    "b.sc": "B.Sc",
    "mba": "MBA",
    "mtech": "M.Tech",
    "m.tech": "M.Tech",
    "mbbs": "MBBS",
    "bcom": "B.Com",
    "b.com": "B.Com",
}


def canonical_course_name(course: str | None) -> str | None:
    if not course:
        return None
    lowered = course.strip().lower()
    return COURSE_ALIASES.get(lowered, course.strip())
