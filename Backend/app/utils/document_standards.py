from __future__ import annotations

import re
from enum import Enum
from typing import Any


class StandardDocumentType(str, Enum):
    INCOME_CERTIFICATE = "Income Certificate"
    CASTE_CERTIFICATE = "Caste Certificate"
    CASTE_VALIDITY_CERTIFICATE = "Caste Validity Certificate"
    DOMICILE_CERTIFICATE = "Domicile Certificate"
    NATIONALITY_CERTIFICATE = "Nationality Certificate"
    AADHAAR_IDENTITY_PROOF = "Aadhaar / Identity Proof"
    ACADEMIC_MARKSHEETS = "Academic Marksheets"
    ADMISSION_BONAFIDE = "Admission / Bonafide Certificate"
    BANK_PASSBOOK = "Bank Passbook"
    PASSPORT_PHOTOGRAPH = "Passport-size Photograph"
    DISABILITY_CERTIFICATE = "Disability Certificate"
    OTHER_SUPPORTING = "Other Supporting Documents"


ALL_STANDARD_DOCUMENT_TYPES = tuple(t.value for t in StandardDocumentType)


class DocumentVerificationStatus(str, Enum):
    MISSING = "missing"
    UPLOADED = "uploaded"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


# Rule-based patterns for mapping scholarship free-text requirements
_PATTERNS = [
    (
        StandardDocumentType.INCOME_CERTIFICATE,
        re.compile(r"\b(income\s+(?:certificate|proof|declaration)|tahsildar|income)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.CASTE_VALIDITY_CERTIFICATE,
        re.compile(r"\b(caste\s+validity|validity\s+certificate)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.CASTE_CERTIFICATE,
        re.compile(r"\b(caste|community|category|tribe)\s+(?:certificate|proof)?\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.DOMICILE_CERTIFICATE,
        re.compile(r"\b(domicile|residential|residence\s+proof)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.NATIONALITY_CERTIFICATE,
        re.compile(r"\b(nationality|citizenship)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.AADHAAR_IDENTITY_PROOF,
        re.compile(r"\b(aadhaar|aadhar|identity|id\s+proof|ration\s+card|voter|pan\s+card)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.ACADEMIC_MARKSHEETS,
        re.compile(
            r"\b(marksheet|mark\s*sheet|previous\s+(?:year|mark)|rank\s*card|scorecard|class\s*(?:7|8|10|12)|grade\s*sheet)\b",
            re.IGNORECASE,
        ),
    ),
    (
        StandardDocumentType.ADMISSION_BONAFIDE,
        re.compile(
            r"\b(admission|bonafide|allotment|cap\s+allotment|fee\s+receipt|tuition|enrollment|college\s+id)\b",
            re.IGNORECASE,
        ),
    ),
    (
        StandardDocumentType.BANK_PASSBOOK,
        re.compile(r"\b(bank|passbook|account\s+details|cheque)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.PASSPORT_PHOTOGRAPH,
        re.compile(r"\b(photo|photograph|passport\s+size)\b", re.IGNORECASE),
    ),
    (
        StandardDocumentType.DISABILITY_CERTIFICATE,
        re.compile(r"\b(disability|udid|pwd|handicap|blindness|locomotor)\b", re.IGNORECASE),
    ),
]


def normalize_document_type(raw_type: str | None) -> str:
    """Normalize arbitrary document type names to a standardized category."""
    if not raw_type or not str(raw_type).strip():
        return StandardDocumentType.OTHER_SUPPORTING.value

    clean = str(raw_type).strip()
    # Direct match against standard types
    for standard in ALL_STANDARD_DOCUMENT_TYPES:
        if clean.lower() == standard.lower():
            return standard

    # Pattern based match
    for standard_type, pattern in _PATTERNS:
        if pattern.search(clean):
            return standard_type.value

    return StandardDocumentType.OTHER_SUPPORTING.value


def parse_scholarship_required_documents(raw_text: str | None) -> list[dict[str, Any]]:
    """Parse a scholarship's required_documents free-text into discrete requirements.

    Preserves exact official clause names while mapping them to standardized categories.
    If no text is specified, returns standard baseline requirements.
    """
    if not raw_text or not str(raw_text).strip():
        # Fallback baseline when scheme does not specify custom documents
        return [
            {
                "document_name": "Identity Proof (Aadhaar)",
                "standard_type": StandardDocumentType.AADHAAR_IDENTITY_PROOF.value,
                "original_text": "Aadhaar / Identity Proof",
                "is_standard": True,
                "is_fallback": True,
            },
            {
                "document_name": "Income Certificate",
                "standard_type": StandardDocumentType.INCOME_CERTIFICATE.value,
                "original_text": "Income Certificate",
                "is_standard": True,
                "is_fallback": True,
            },
            {
                "document_name": "Academic Marksheets",
                "standard_type": StandardDocumentType.ACADEMIC_MARKSHEETS.value,
                "original_text": "Academic Marksheets",
                "is_standard": True,
                "is_fallback": True,
            },
        ]

    # Split by commas, semicolons, bullets, and newlines
    tokens = re.split(r"[,;\n•\r]+|\band\b", str(raw_text), flags=re.IGNORECASE)
    results = []
    seen = set()

    for token in tokens:
        clean = token.strip(" \t:.-*")
        if not clean or len(clean) < 3:
            continue
        # Avoid duplicate requirements within the same scholarship
        lower_key = clean.lower()
        if lower_key in seen:
            continue
        seen.add(lower_key)

        standard_type = normalize_document_type(clean)
        is_standard = standard_type != StandardDocumentType.OTHER_SUPPORTING.value

        results.append(
            {
                "document_name": clean,
                "standard_type": standard_type,
                "original_text": clean,
                "is_standard": is_standard,
                "is_fallback": False,
            }
        )

    if not results:
        return parse_scholarship_required_documents(None)

    return results
