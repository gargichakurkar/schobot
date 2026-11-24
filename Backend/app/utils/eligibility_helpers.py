from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any


def normalize_option(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def numeric_from_text(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def extract_max_income(text: str) -> float | None:
    if not text:
        return None
    lowered = text.lower()
    for pattern in (
        r"income.*?(?:less than|upto|up to|below|not exceed|under|within|<=|<)\s*₹?\s*(\d+(?:,\d+)*(?:\.\d+)?)",
        r"₹\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:per annum|per year|annually)",
        r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:lakh|lac|lacs|k)",
    ):
        match = re.search(pattern, lowered)
        if match:
            value = match.group(1).replace(",", "")
            if "lakh" in lowered or "lac" in lowered or "lacs" in lowered:
                return float(value) * 100000
            if "k" in lowered and "lak" not in lowered:
                return float(value) * 1000
            return float(value)
    return None


def extract_min_percentage(text: str) -> float | None:
    if not text:
        return None
    lowered = text.lower()
    patterns = [
        r"minimum(?:\s+required)?\s+(?:percentage|marks|score)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        r"at\s+least\s*(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s*(?:and above|or above|minimum)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1))
    return None


def likely_valid_url(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith("http://") or value.startswith("https://")
