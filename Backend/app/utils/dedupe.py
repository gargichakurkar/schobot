from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def dedupe_by_scholarship_id(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Keep the first API result for each stable scholarship ID, in input order."""
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        scholarship_id = record.get("scholarship_id", record.get("id"))
        if scholarship_id is None:
            # An unidentified result cannot safely be treated as the same award.
            unique.append(dict(record))
            continue
        key = str(scholarship_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(record))
    return unique
