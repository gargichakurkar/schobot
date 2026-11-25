from __future__ import annotations

import argparse
import json
import logging
import re
import ssl
import time
from datetime import datetime, time as day_time, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from hashlib import sha256
from io import BytesIO
from threading import Event
from typing import Any
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import certifi
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, SessionLocal
from app.models.scholarship_ingestion import (
    ScholarshipIngestionEvent,
    ScholarshipIngestionRun,
    ScholarshipIngestionSource,
    ScholarshipIngestionState,
)
from app.models.scholarship import Scholarship
from app.seed.import_scholarships import map_dual_row
from app.services.scholarship_fetcher.source_config import (
    ENABLED_SOURCE_KEYS,
    NSP_URL,
    SOURCES,
    enabled_sources,
    is_approved_https_url,
)

SOURCE_FILENAME = "nsp_all_scholarships"
RETRY_COUNT = 4
RETRY_MAX_DELAY_SECONDS = 30
SCHEDULE_INTERVAL_SECONDS = 24 * 60 * 60
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
ROBOTS_CACHE_SECONDS = 24 * 60 * 60
MAX_GUIDELINE_TEXT_CHARS = 500_000
MAX_AI_CONTEXT_CHARS = 18_000
MAX_GUIDELINE_PAGES = 100
GUIDELINE_REQUEST_INTERVAL_SECONDS = 1
DATASET_COLUMNS = (
    "scholarship_name",
    "offered_by",
    "current_education",
    "eligible_castes_or_categories",
    "minimum_marks",
    "family_income_limit",
    "gender_restrictions",
    "benefits_provided",
    "key_documents_required",
    "official_portal_link",
    "scheme_info_link",
    "Type",
    "State",
)
CONTENT_CLASSIFICATIONS = {"NEW", "UNCHANGED", "UPDATED", "REVIEW_REQUIRED", "FAILED"}
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
FETCHER_USER_AGENT = "ScholarMateScholarshipFetcher/1.0"
HEADERS = {
    "User-Agent": FETCHER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Connection": "close",
}

logger = logging.getLogger(__name__)
_ROBOTS_CACHE: dict[tuple[str, str], tuple[float, RobotFileParser]] = {}

_GUIDELINE_URL_PLACEHOLDERS = {
    "",
    "#",
    "-",
    "0",
    "about:blank",
    "javascript:void(0)",
    "missing",
    "na",
    "n/a",
    "n.a.",
    "nan",
    "nil",
    "no_file",
    "no_guideline",
    "no_link",
    "no_url",
    "none",
    "not_applicable",
    "not_available",
    "not_found",
    "not_provided",
    "null",
    "placeholder",
    "undefined",
    "unknown",
}


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    def __init__(self, source_key: str = "nsp"):
        super().__init__()
        self.source_key = source_key

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target_url = urljoin(req.full_url, newurl)
        if not _is_allowed_official_url(target_url, self.source_key):
            raise ValueError(
                f"Refusing redirect outside approved HTTPS domains: {target_url}"
            )
        return super().redirect_request(
            req,
            fp,
            code,
            msg,
            headers,
            target_url,
        )


def urlopen(request, timeout=60, context=None, source_key: str = "nsp"):
    opener = build_opener(
        _AllowlistedRedirectHandler(source_key),
        HTTPSHandler(context=context or SSL_CONTEXT),
    )
    return opener.open(request, timeout=timeout)


def _is_placeholder_guideline_url(value: Any) -> bool:
    if value is None:
        return True

    def normalize(candidate: str) -> str:
        return re.sub(r"[\s-]+", "_", candidate.strip().casefold()).rstrip("/")

    candidate = str(value).strip()
    if not candidate:
        return True

    if normalize(candidate) in _GUIDELINE_URL_PLACEHOLDERS:
        return True

    try:
        path = urlsplit(candidate).path
    except ValueError:
        return True
    path_segments = [segment for segment in unquote(path).split("/") if segment]
    if not path_segments:
        return False
    final_segment = normalize(path_segments[-1])
    filename = (
        final_segment.rsplit(".", 1)[0]
        if "." in final_segment
        else final_segment
    )
    return (
        final_segment in _GUIDELINE_URL_PLACEHOLDERS
        or filename in _GUIDELINE_URL_PLACEHOLDERS
    )


def _is_allowed_official_url(url: str, source_key: str = "nsp") -> bool:
    return is_approved_https_url(url, source_key=source_key)


def _assert_robots_allowed(url: str, source_key: str) -> None:
    parsed = urlsplit(url)
    origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    cache_key = (source_key, origin)
    cached = _ROBOTS_CACHE.get(cache_key)
    now = time.monotonic()
    if cached is None or cached[0] <= now:
        robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
        parser = RobotFileParser(robots_url)
        try:
            request = Request(robots_url, headers=HEADERS)
            with urlopen(
                request,
                timeout=30,
                context=SSL_CONTEXT,
                source_key=source_key,
            ) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise RuntimeError(
                        f"Unable to verify robots policy for {origin}: HTTP {status}"
                    )
                content = response.read(MAX_ROBOTS_BYTES + 1)
                if len(content) > MAX_ROBOTS_BYTES:
                    raise RuntimeError(
                        f"robots.txt from {origin} exceeds the size limit"
                    )
                parser.parse(content.decode("utf-8-sig", "replace").splitlines())
        except HTTPError as exc:
            if exc.code != 404:
                raise RuntimeError(
                    f"Unable to verify robots policy for {origin}: HTTP {exc.code}"
                ) from exc
            parser.parse([])
        _ROBOTS_CACHE[cache_key] = (
            now + ROBOTS_CACHE_SECONDS,
            parser,
        )
    else:
        parser = cached[1]

    if not parser.can_fetch(FETCHER_USER_AGENT, url):
        raise PermissionError(
            f"Robots policy disallows fetching {url} for {FETCHER_USER_AGENT}."
        )


def _retry_after_seconds(error: HTTPError) -> float | None:
    headers = error.headers
    value = headers.get("Retry-After") if headers is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(
            0.0,
            (retry_at - datetime.now(timezone.utc)).total_seconds(),
        )


def _fetch_resource_details(
    url: str,
    retries: int = RETRY_COUNT,
    validators: dict[str, str | None] | None = None,
    source_key: str = "nsp",
) -> tuple[bytes, str, str, str | None, str | None]:
    if not _is_allowed_official_url(url, source_key):
        raise ValueError(f"Refusing to fetch non-official or non-HTTPS URL: {url}")
    if retries < 1:
        raise ValueError("retries must be at least one")
    _assert_robots_allowed(url, source_key)

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        retry_after: float | None = None
        try:
            request_headers = dict(HEADERS)
            if validators:
                if validators.get("etag"):
                    request_headers["If-None-Match"] = validators["etag"]
                if validators.get("last_modified"):
                    request_headers["If-Modified-Since"] = validators["last_modified"]
            request = Request(url, headers=request_headers)
            with urlopen(
                request,
                timeout=60,
                context=SSL_CONTEXT,
                source_key=source_key,
            ) as response:
                status = getattr(response, "status", 200)
                if status < 200 or status >= 300:
                    raise URLError(f"Official site returned HTTP {status}")
                final_url = response.geturl()
                if not _is_allowed_official_url(final_url, source_key):
                    raise ValueError(f"Refusing redirected URL outside official domains: {final_url}")
                content_type = response.headers.get("Content-Type", "")
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise ValueError(f"Response from {url} exceeds the download size limit")
                return (
                    content,
                    content_type,
                    final_url,
                    response.headers.get("ETag"),
                    response.headers.get("Last-Modified"),
                )
        except HTTPError as exc:
            if exc.code == 304:
                response_headers = exc.headers or {}
                return (
                    b"",
                    response_headers.get("Content-Type", ""),
                    url,
                    response_headers.get("ETag")
                    or (validators or {}).get("etag"),
                    response_headers.get("Last-Modified")
                    or (validators or {}).get("last_modified"),
                )
            if exc.code < 500 and exc.code != 429:
                logger.error("Non-retryable HTTP %s fetching %s", exc.code, url)
                raise
            last_error = exc
            if exc.code == 429:
                retry_after = _retry_after_seconds(exc)
                if (
                    retry_after is not None
                    and retry_after > RETRY_MAX_DELAY_SECONDS
                ):
                    raise RuntimeError(
                        "The source requested a retry delay longer than the "
                        "configured limit; deferring this fetch to the next run."
                    ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc

        logger.warning(
            "Fetch attempt %s/%s failed for %s: %s",
            attempt,
            retries,
            url,
            last_error,
        )
        if attempt < retries:
            delay = (
                retry_after
                if retry_after is not None
                else min(2 ** (attempt - 1), RETRY_MAX_DELAY_SECONDS)
            )
            time.sleep(delay)

    if last_error is None:
        raise RuntimeError(f"Unable to fetch {url}")
    raise RuntimeError(f"Unable to fetch {url} after {retries} attempts") from last_error


def fetch_resource(
    url: str,
    retries: int = RETRY_COUNT,
    source_key: str = "nsp",
) -> tuple[bytes, str, str]:
    content, content_type, final_url, _, _ = _fetch_resource_details(
        url,
        retries=retries,
        source_key=source_key,
    )
    return content, content_type, final_url


def fetch_page(retries: int = RETRY_COUNT) -> str:
    content, _, _ = fetch_resource(NSP_URL, retries=retries)
    return content.decode("utf-8-sig", "replace")


def normalize_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()


def extract_scheme_name(text: str) -> str | None:
    text = re.sub(r"\s+", " ", text).strip()

    # NSP labels each scheme as Merit Based or Welfare Based.
    match = re.search(
        r"\s+\((?:Merit Based|Welfare Based) Scheme\)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        name = text[:match.start()].strip()
        return name or None

    # Fallback for cards with a different label format.
    match = re.search(r"\s+Scheme\s+Open from\s*:", text, re.IGNORECASE)
    if match:
        name = text[:match.start()].strip()
        return name or None

    return None


def _status_from_deadline_label(status_label: str, deadline: str) -> str:
    if "closed" in status_label.casefold():
        return "closed"
    parsed_deadline = _parse_deadline(deadline)
    if parsed_deadline and parsed_deadline.date() < datetime.now(timezone.utc).date():
        return "closed"
    return "open"


def extract_schemes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    schemes = []
    seen = set()

    for group in soup.select(".accordion-item"):
        provider_node = group.select_one(".accordion-header")
        provider = provider_node.get_text(" ", strip=True) if provider_node else None

        for card in group.select(".accordion-body > .row.mb-4"):
            text = card.get_text(" ", strip=True)
            name = extract_scheme_name(text)

            if not name:
                logger.warning("Could not identify scheme name: %s", text[:180])
                continue

            key = (normalize_name(name), normalize_name(provider or ""))
            if not key[0] or key in seen:
                continue
            seen.add(key)

            links = {}
            for anchor in card.find_all("a", href=True):
                label = anchor.get_text(" ", strip=True).casefold()

                if "specification" in label or "guideline" in label:
                    raw_href = anchor["href"]
                    if not _is_placeholder_guideline_url(raw_href):
                        links["guideline_url"] = urljoin(NSP_URL, raw_href)
                elif label == "faq":
                    links["faq_url"] = urljoin(NSP_URL, anchor["href"])
                elif label in {"apply", "apply now", "application portal"}:
                    links["official_url"] = urljoin(NSP_URL, anchor["href"])

            deadline_match = re.search(
                r"Student Application\s*(?P<status>Open till|Closed on)\s*:\s*"
                r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})",
                text,
                re.IGNORECASE,
            )
            application_start_match = re.search(
                r"Student Application\s+Open from\s*:\s*"
                r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})",
                text,
                re.IGNORECASE,
            )

            schemes.append({
                "scholarship_name": name,
                "provider": provider,
                "official_link": links.get("official_url"),
                "scheme_info_link": links.get("guideline_url"),
                "faq_link": links.get("faq_url"),
                "application_deadline": (
                    deadline_match.group("date") if deadline_match else None
                ),
                "application_start_date": (
                    application_start_match.group("date")
                    if application_start_match
                    else None
                ),
                "application_start_evidence": (
                    application_start_match.group(0)
                    if application_start_match
                    else None
                ),
                "application_status": (
                    _status_from_deadline_label(
                        deadline_match.group("status"),
                        deadline_match.group("date"),
                    )
                    if deadline_match
                    else "unknown"
                ),
                "deadline_evidence": deadline_match.group(0) if deadline_match else None,
                "listing_text": text,
                "source_url": NSP_URL,
            })

    return schemes


def _source_identifier(scheme: dict[str, Any]) -> str:
    identity = "|".join(
        (
            normalize_name(scheme.get("scholarship_name") or ""),
            normalize_name(scheme.get("provider") or ""),
        )
    )
    return f"nsp:{sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _normalized_official_url(value: Any) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(str(value).strip())
        host = (parsed.hostname or "").casefold().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.casefold() != "https" or not host:
        return None
    netloc = host if port in {None, 443} else f"{host}:{port}"
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", netloc, path, parsed.query, parsed.fragment))


def _tokens(value: str | None) -> set[str]:
    return {token.strip() for token in (value or "").split(";") if token.strip()}


def _load_existing_records(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "name": record.scholarship_name,
            "provider": record.provider,
            "source_filename": record.source_filename,
            "source_identifier": record.source_identifier,
            "official_link": record.official_link,
            "normalized": normalize_name(record.scholarship_name or ""),
            "provider_normalized": normalize_name(record.provider or ""),
        }
        for record in db.query(Scholarship).all()
        if record.scholarship_name
    ]


def _classify_schemes(
    schemes: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    exact_matches: list[dict[str, Any]] = []
    review_schemes: list[dict[str, Any]] = []
    new_schemes: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()

    def education_level(name: str) -> str | None:
        normalized = normalize_name(name)
        for level in (
            "diploma",
            "degree",
            "post matric",
            "pre matric",
            "undergraduate",
            "postgraduate",
        ):
            if level in normalized:
                return level
        words = set(normalized.split())
        if "ug" in words:
            return "ug"
        if "pg" in words:
            return "pg"
        return None

    for scheme in schemes:
        name = scheme["scholarship_name"]
        normalized = normalize_name(name)
        provider = normalize_name(scheme.get("provider") or "")
        source_id = _source_identifier(scheme)

        if source_id in seen_source_ids:
            exact_matches.append({"scheme": scheme, "action": "duplicate_in_feed"})
            continue
        seen_source_ids.add(source_id)

        source_match = next(
            (
                record
                for record in existing
                if SOURCE_FILENAME in _tokens(record.get("source_filename"))
                and source_id in _tokens(record.get("source_identifier"))
            ),
            None,
        )
        if source_match:
            exact_matches.append(
                {
                    "scheme": scheme,
                    "matched_name": source_match["name"],
                    "matched_id": source_match["id"],
                    "action": "update",
                }
            )
            continue

        official_link = _normalized_official_url(scheme.get("official_link"))
        generic_listing_link = _normalized_official_url(NSP_URL)
        url_matches = [
            record
            for record in existing
            if official_link
            and official_link != generic_listing_link
            and _normalized_official_url(record.get("official_link")) == official_link
        ]
        if url_matches:
            review_schemes.append(
                {
                    "scheme": scheme,
                    "possible_matches": [
                        {
                            "matched_name": record["name"],
                            "similarity": 1.0,
                            "match_reason": "official_url",
                        }
                        for record in url_matches[:3]
                    ],
                }
            )
            continue

        exact = next(
            (
                record
                for record in existing
                if record["normalized"] == normalized
                and (
                    not provider
                    or not record["provider_normalized"]
                    or provider == record["provider_normalized"]
                )
            ),
            None,
        )
        if exact:
            exact_matches.append(
                {
                    "scheme": scheme,
                    "matched_name": exact["name"],
                    "matched_id": exact["id"],
                    "action": "exact_existing",
                }
            )
            continue

        possible = []
        for record in existing:
            old_level = education_level(record["name"])
            new_level = education_level(name)
            if old_level and new_level and old_level != new_level:
                continue

            name_score = SequenceMatcher(
                None, normalized, record["normalized"]
            ).ratio()
            provider_score = (
                SequenceMatcher(
                    None, provider, record["provider_normalized"]
                ).ratio()
                if provider and record["provider_normalized"]
                else 0
            )
            score = (
                0.85 * name_score + 0.15 * provider_score
                if provider_score
                else name_score
            )
            if score >= 0.78:
                possible.append(
                    {
                        "matched_name": record["name"],
                        "similarity": round(score, 3),
                    }
                )

        if possible:
            possible.sort(key=lambda item: item["similarity"], reverse=True)
            review_schemes.append(
                {"scheme": scheme, "possible_matches": possible[:3]}
            )
        else:
            new_schemes.append(scheme)

    return new_schemes, review_schemes, exact_matches


def find_new_schemes(
    schemes: list[dict[str, Any]],
    db: Session | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], int]:
    if db is not None:
        existing = _load_existing_records(db)
        new, review, exact = _classify_schemes(schemes, existing)
        return new, review, exact, len(existing)

    with SessionLocal() as session:
        existing = _load_existing_records(session)
    new, review, exact = _classify_schemes(schemes, existing)
    return new, review, exact, len(existing)


GUIDELINE_LABELS = {
    "benefits": (
        "benefits",
        "benefits provided",
        "scholarship amount",
        "financial assistance",
        "stipend",
    ),
    "income_text": (
        "family income",
        "annual income",
        "income limit",
        "income ceiling",
        "parental income",
    ),
    "category": (
        "eligible categories",
        "eligible category",
        "caste/category",
        "caste and category",
        "community",
        "eligible caste",
    ),
    "eligible_level": (
        "eligible education",
        "course of study",
        "level of study",
        "eligible course",
        "academic level",
    ),
    "required_documents": (
        "documents required",
        "required documents",
        "documents to be submitted",
        "supporting documents",
    ),
    "minimum_marks_text": (
        "minimum marks",
        "minimum percentage",
        "academic requirement",
        "minimum qualifying marks",
    ),
    "gender_requirement": (
        "gender",
        "gender eligibility",
        "eligible gender",
    ),
    "scholarship_type": ("scholarship type", "scheme type", "type of scholarship"),
    "state": ("state", "domicile", "residents of", "resident of"),
    "application_start": ("student application open from",),
    "application_deadline": (
        "student application open till",
        "student application closed on",
        "last date for submission",
    ),
}


def _extract_labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(
        sorted((re.escape(label) for label in labels), key=len, reverse=True)
    )
    any_label_pattern = "|".join(
        sorted(
            (re.escape(label) for group in GUIDELINE_LABELS.values() for label in group),
            key=len,
            reverse=True,
        )
    )
    lines = text.splitlines()
    for index, line in enumerate(lines):
        cleaned_line = re.sub(r"^\s*(?:[•*]\s*|\d+[.)]\s*)", "", line).strip()
        match = re.match(
            rf"^(?:{label_pattern})\s*(?:[:\-–]\s*(.*?))?\s*$",
            cleaned_line,
            re.IGNORECASE,
        )
        if not match:
            continue
        value = (match.group(1) or "").strip()
        if not value:
            collected: list[str] = []
            for candidate in lines[index + 1 :]:
                candidate = candidate.strip()
                if not candidate:
                    if collected:
                        break
                    continue
                if re.match(r"^(?:[A-Z][A-Z\s/&()'-]{2,}|[^:]{1,80}:)\s*$", candidate):
                    break
                if re.match(
                    rf"^(?:{any_label_pattern})\s*[:\-–]",
                    candidate,
                    re.IGNORECASE,
                ):
                    break
                collected.append(candidate)
            value = " ".join(collected)
        value = re.sub(r"\s+", " ", value).strip()
        return value or None
    return None


def _extract_guideline_document(
    content: bytes,
    content_type: str,
) -> tuple[dict[str, str], str, bool]:
    is_pdf = "pdf" in content_type.casefold() or content.startswith(b"%PDF-")
    was_truncated = False
    if is_pdf:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "The pypdf dependency is required to extract NSP PDF guidelines."
            ) from exc

        reader = PdfReader(BytesIO(content), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("The official guideline PDF is encrypted.")
        page_text = []
        for page_number, page in enumerate(reader.pages):
            if page_number >= MAX_GUIDELINE_PAGES:
                logger.warning(
                    "Guideline PDF exceeds the %s-page extraction limit",
                    MAX_GUIDELINE_PAGES,
                )
                was_truncated = True
                break
            page_text.append(page.extract_text() or "")
        text = "\n".join(page_text)
    else:
        charset_match = re.search(r"charset=([\w.-]+)", content_type, re.IGNORECASE)
        encoding = charset_match.group(1) if charset_match else "utf-8-sig"
        try:
            html = content.decode(encoding, "replace")
        except LookupError:
            html = content.decode("utf-8-sig", "replace")
        text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return {}, "", was_truncated

    if len(text) > MAX_GUIDELINE_TEXT_CHARS:
        logger.warning(
            "Guideline text exceeds the %s-character storage limit; marking it partial",
            MAX_GUIDELINE_TEXT_CHARS,
        )
        text = text[:MAX_GUIDELINE_TEXT_CHARS]
        was_truncated = True

    fields = {
        key: value
        for key, labels in GUIDELINE_LABELS.items()
        if (value := _extract_labeled_value(text, labels))
    }
    deadline_date, deadline_status, deadline_evidence = _extract_document_deadline(text)
    if deadline_date:
        fields["application_deadline"] = deadline_date
        fields["application_status"] = deadline_status
        fields["deadline_evidence"] = deadline_evidence or ""
    start_date, start_evidence = _extract_document_application_start(text)
    if start_date:
        fields["application_start_date"] = start_date
        fields["application_start_evidence"] = start_evidence or ""
    fields["eligibility_details"] = text
    return fields, text, was_truncated


def extract_guideline_fields(content: bytes, content_type: str) -> dict[str, str]:
    fields, _, _ = _extract_guideline_document(content, content_type)
    return fields


def fetch_guidelines(
    url: str | None,
    retries: int = RETRY_COUNT,
    source_key: str = "nsp",
) -> dict[str, str]:
    if _is_placeholder_guideline_url(url):
        return {}
    content, content_type, final_url, _, _ = _fetch_resource_details(
        url,
        retries=retries,
        source_key=source_key,
    )
    logger.info("Extracting official guideline content from %s", final_url)
    return extract_guideline_fields(content, content_type)


def _normalize_excerpt(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _extract_document_deadline(text: str) -> tuple[str | None, str, str | None]:
    match = re.search(
        r"\bStudent\s+Application\s+"
        r"(?P<status>Open\s+till|Closed\s+on|Last\s+date(?:\s+for\s+submission)?)"
        r"\s*[:\-]?\s*(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, "unknown", None
    status = _status_from_deadline_label(match.group("status"), match.group("date"))
    return match.group("date"), status, match.group(0)


def _extract_document_application_start(
    text: str,
) -> tuple[str | None, str | None]:
    match = re.search(
        r"\bStudent\s+Application\s+Open\s+from\s*[:\-]?\s*"
        r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None, None
    return match.group("date"), match.group(0)


def _dataset_fields_from_sources(
    scheme: dict[str, Any],
    guideline_fields: dict[str, str],
    source_text: str,
) -> dict[str, str | None]:
    fields: dict[str, str | None] = {column: None for column in DATASET_COLUMNS}
    fields["scholarship_name"] = scheme.get("scholarship_name")
    fields["offered_by"] = scheme.get("provider")
    fields["current_education"] = guideline_fields.get("eligible_level")
    fields["eligible_castes_or_categories"] = guideline_fields.get("category")
    fields["minimum_marks"] = guideline_fields.get("minimum_marks_text")
    fields["family_income_limit"] = guideline_fields.get("income_text")
    fields["gender_restrictions"] = guideline_fields.get("gender_requirement")
    fields["benefits_provided"] = guideline_fields.get("benefits")
    fields["key_documents_required"] = guideline_fields.get("required_documents")
    fields["official_portal_link"] = (
        scheme.get("official_link")
        or (NSP_URL if scheme.get("source_url", NSP_URL) == NSP_URL else None)
    )
    fields["scheme_info_link"] = scheme.get("scheme_info_link")
    fields["Type"] = guideline_fields.get("scholarship_type")
    fields["State"] = guideline_fields.get("state")

    provider = str(fields["offered_by"] or "").casefold()
    if not fields["Type"] and any(
        term in provider for term in ("ministry", "government", "department")
    ):
        fields["Type"] = "Government"

    combined_text = "\n".join(part for part in (scheme.get("listing_text"), source_text) if part)
    for column, key in (
        ("current_education", "eligible_level"),
        ("eligible_castes_or_categories", "category"),
        ("minimum_marks", "minimum_marks_text"),
        ("family_income_limit", "income_text"),
        ("gender_restrictions", "gender_requirement"),
        ("benefits_provided", "benefits"),
        ("key_documents_required", "required_documents"),
        ("Type", "scholarship_type"),
        ("State", "state"),
    ):
        if not fields[column] and (value := _extract_labeled_value(
            combined_text, GUIDELINE_LABELS[key]
        )):
            fields[column] = value

    return {
        column: re.sub(r"\s+", " ", str(value)).strip() if value else None
        for column, value in fields.items()
    }


def _validate_dataset_fields(
    fields: dict[str, Any],
    source_key: str = "nsp",
) -> tuple[bool, str | None]:
    if tuple(fields) != DATASET_COLUMNS:
        return False, "Dataset field names or ordering do not match the 13-column contract."
    if not str(fields.get("scholarship_name") or "").strip():
        return False, "Scholarship name is missing."
    for column in DATASET_COLUMNS:
        value = fields[column]
        if value is not None and not isinstance(value, str):
            return False, f"{column} must be a string or null."
    for column, limit in (
        ("scholarship_name", 255),
        ("offered_by", 255),
        ("official_portal_link", 500),
        ("scheme_info_link", 500),
        ("Type", 100),
        ("State", 100),
    ):
        value = fields.get(column)
        if value and len(value) > limit:
            return False, f"{column} exceeds the existing Scholarship model limit."
    for column in ("official_portal_link", "scheme_info_link"):
        value = fields.get(column)
        if value and not is_approved_https_url(value, source_key=source_key):
            return False, f"{column} is outside the approved HTTPS source domains."
    return True, None


def _create_groq_client():
    if not settings.groq_api_key:
        return None
    from groq import Groq

    return Groq(api_key=settings.groq_api_key)


def _extract_missing_fields_with_ai(
    fields: dict[str, str | None],
    source_text: str,
    client: Any,
) -> dict[str, str | None]:
    if not client or not source_text:
        return fields
    missing = [
        column for column in DATASET_COLUMNS
        if column not in {"scholarship_name", "offered_by", "official_portal_link", "scheme_info_link"}
        and not fields.get(column)
    ]
    if not missing:
        return fields

    prompt = (
        "Extract scholarship fields from the supplied official source text. "
        "Return a JSON object with exactly these 13 keys, in this order: "
        f"{json.dumps(DATASET_COLUMNS)}. Use only exact source text excerpts as values; "
        "use null when absent. Never infer, paraphrase, complete, or translate. "
        "Do not generate links. Preserve scholarship and provider names exactly. "
        f"Already verified fields: {json.dumps(fields, ensure_ascii=False)}\n"
        f"Official source text:\n{source_text[:MAX_AI_CONTEXT_CHARS]}"
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": "You are a conservative data extractor. Never infer missing facts.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    extracted = json.loads(content or "")
    if not isinstance(extracted, dict) or set(extracted) != set(DATASET_COLUMNS):
        raise ValueError("AI extraction did not return the exact 13-column object.")

    merged = dict(fields)
    fixed_fields = {
        "scholarship_name",
        "offered_by",
        "official_portal_link",
        "scheme_info_link",
    }
    source_normalized = _normalize_excerpt(source_text)
    for column in DATASET_COLUMNS:
        value = extracted[column]
        if column in fixed_fields:
            continue
        if value is None or (
            isinstance(value, str)
            and value.strip().casefold() in {"", "unknown", "not specified", "n/a", "none"}
        ):
            continue
        if not isinstance(value, str):
            raise ValueError(f"AI returned a non-text value for {column}.")
        value = re.sub(r"\s+", " ", value).strip()
        if value and _normalize_excerpt(value) not in source_normalized:
            raise ValueError(f"AI value for {column} is not an exact source excerpt.")
        if not merged.get(column):
            merged[column] = value or None
    return merged


def _parse_deadline(value: str | None) -> datetime | None:
    if not value:
        return None
    for format_string in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            parsed = datetime.strptime(value, format_string).date()
            return datetime.combine(parsed, day_time.max, tzinfo=timezone.utc)
        except ValueError:
            continue
    logger.warning("Ignoring unrecognized NSP deadline: %s", value)
    return None


def _record_from_scheme(scheme: dict[str, Any]) -> dict[str, Any]:
    source_id = _source_identifier(scheme)
    dataset_fields = scheme.get("_dataset_fields")
    if dataset_fields:
        record = map_dual_row(dataset_fields)
        if len(dataset_fields.get("current_education") or "") > 150:
            record["eligible_level"] = None
        record["dataset_id"] = f"{SOURCE_FILENAME}::{source_id}"
        record["source_filename"] = SOURCE_FILENAME
        record["source_identifier"] = source_id
        record["deadline"] = scheme.get("deadline") or _parse_deadline(
            scheme.get("application_deadline")
        )
        if scheme.get("_guideline_fields", {}).get("eligibility_details"):
            record["eligibility_details"] = scheme["_guideline_fields"][
                "eligibility_details"
            ]
        record.pop("active_status", None)
        record.pop("is_active", None)
        return {
            key: value
            for key, value in record.items()
            if value is not None and value != ""
        }

    record: dict[str, Any] = {
        "dataset_id": f"{SOURCE_FILENAME}::{source_id}",
        "scholarship_name": scheme["scholarship_name"],
        "provider": scheme.get("provider"),
        "category": scheme.get("category"),
        "income_text": scheme.get("income_text"),
        "eligible_level": scheme.get("eligible_level"),
        "benefits": scheme.get("benefits"),
        "required_documents": scheme.get("required_documents"),
        "eligibility_details": scheme.get("eligibility_details"),
        "official_link": scheme.get("official_link"),
        "scheme_info_link": scheme.get("scheme_info_link"),
        "minimum_marks_text": scheme.get("minimum_marks_text"),
        "gender_requirement": scheme.get("gender_requirement"),
        "deadline": scheme.get("deadline") or _parse_deadline(scheme.get("application_deadline")),
        "source_filename": SOURCE_FILENAME,
        "source_identifier": source_id,
    }
    return {
        key: value
        for key, value in record.items()
        if value is not None and value != ""
    }


def _apply_scheme_update(
    scholarship: Scholarship,
    record: dict[str, Any],
) -> bool:
    changed = False
    for field, value in record.items():
        if field in {"source_filename", "source_identifier"}:
            continue
        if field == "dataset_id" and scholarship.dataset_id:
            continue
        if value is not None and value != "" and getattr(scholarship, field) != value:
            setattr(scholarship, field, value)
            changed = True

    for field in ("source_filename", "source_identifier"):
        combined = _tokens(getattr(scholarship, field)) | _tokens(record.get(field))
        value = "; ".join(sorted(combined))
        if value != getattr(scholarship, field):
            setattr(scholarship, field, value)
            changed = True
    return changed


def persist_schemes(
    schemes: list[dict[str, Any]],
    session_factory=None,
) -> dict[str, int]:
    make_session = session_factory or SessionLocal
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    try:
        with make_session() as db:
            with db.begin():
                for scheme in schemes:
                    existing = _load_existing_records(db)
                    new, review, exact = _classify_schemes([scheme], existing)
                    source_update = next(
                        (item for item in exact if item.get("action") == "update"),
                        None,
                    )

                    if source_update:
                        scholarship = db.get(Scholarship, source_update["matched_id"])
                        if scholarship is None:
                            raise RuntimeError(
                                "NSP source match disappeared during the import transaction."
                            )
                        changed = _apply_scheme_update(
                            scholarship,
                            _record_from_scheme(scheme),
                        )
                        db.flush()
                        stats["updated" if changed else "unchanged"] += 1
                    elif new:
                        record = _record_from_scheme(scheme)
                        record.setdefault("official_link", NSP_URL)
                        scholarship = Scholarship(**record)
                        scholarship.active_status = "unknown"
                        scholarship.is_active = False
                        db.add(scholarship)
                        db.flush()
                        stats["inserted"] += 1
                    else:
                        stats["skipped"] += 1
                        if review:
                            logger.warning(
                                "Skipping NSP scheme pending duplicate review: %s",
                                scheme["scholarship_name"],
                            )
            logger.info("NSP database write summary: %s", stats)
    except Exception:
        logger.exception("NSP database transaction failed; all writes rolled back")
        raise
    return stats


def _enrich_guidelines(schemes: list[dict[str, Any]]) -> None:
    for scheme in schemes:
        guideline_url = scheme.get("scheme_info_link")
        scholarship_name = scheme.get("scholarship_name", "Unknown scholarship")
        if _is_placeholder_guideline_url(guideline_url):
            logger.warning(
                "Skipping unavailable official guideline URL for %s: %r",
                scholarship_name,
                guideline_url,
            )
            continue
        try:
            extracted_fields = fetch_guidelines(guideline_url)
        except Exception:
            logger.warning(
                "Could not fetch or extract official guidelines for %s; "
                "preserving existing scholarship fields",
                scholarship_name,
                exc_info=True,
            )
            continue
        scheme.update(extracted_fields)


def _hash_payload(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


def _listing_hash(scheme: dict[str, Any]) -> str:
    return _hash_payload(
        {
            "name": scheme.get("scholarship_name"),
            "provider": scheme.get("provider"),
            "listing_text": scheme.get("listing_text"),
            "official_link": scheme.get("official_link"),
            "scheme_info_link": scheme.get("scheme_info_link"),
            "application_status": scheme.get("application_status"),
            "application_start_date": scheme.get("application_start_date"),
            "application_deadline": scheme.get("application_deadline"),
        }
    )


def _content_hash(
    scheme: dict[str, Any],
    listing_hash: str,
    document_hash: str | None,
) -> str:
    return _hash_payload(
        {
            "listing_hash": listing_hash,
            "document_hash": document_hash,
            "application_status": scheme.get("application_status", "unknown"),
            "application_start_date": scheme.get("application_start_date"),
            "application_deadline": scheme.get("application_deadline"),
            "guideline_url": scheme.get("scheme_info_link"),
        }
    )


def _ai_source_context(text: str) -> str:
    if len(text) <= MAX_AI_CONTEXT_CHARS:
        return text
    paragraphs = re.split(r"\n{2,}", text)
    keywords = re.compile(
        r"eligib|income|marks|academic|benefit|amount|stipend|document|gender|"
        r"category|caste|application|deadline|domicile|state|course|education",
        re.IGNORECASE,
    )
    ranked = sorted(
        enumerate(paragraphs),
        key=lambda item: len(keywords.findall(item[1])),
        reverse=True,
    )
    selected: set[int] = set()
    size = 0
    for index, paragraph in ranked:
        if not paragraph.strip():
            continue
        if size + len(paragraph) + 2 > MAX_AI_CONTEXT_CHARS:
            continue
        selected.add(index)
        size += len(paragraph) + 2
    context = "\n\n".join(paragraph for index, paragraph in enumerate(paragraphs) if index in selected)
    if len(context) < min(2_000, MAX_AI_CONTEXT_CHARS):
        context = f"{text[:2_000]}\n\n{context}"
    return context[:MAX_AI_CONTEXT_CHARS]


def _process_incremental_scheme(
    scheme: dict[str, Any],
    previous_state: ScholarshipIngestionState | None,
    has_source_record: bool,
    base_classification: str,
    ai_client: Any,
    source_key: str = "nsp",
) -> dict[str, Any]:
    source_id = _source_identifier(scheme)
    listing_hash = _listing_hash(scheme)
    guideline_url = scheme.get("scheme_info_link")
    previous_same_guideline = (
        previous_state is not None
        and previous_state.guideline_url == guideline_url
        and previous_state.document_hash is not None
    )
    guideline_text = ""
    guideline_fields: dict[str, str] = {}
    document_hash: str | None = None
    resolved_guideline_url = guideline_url
    etag = None
    last_modified = None
    document_unchanged = False
    was_truncated = False

    if base_classification == "REVIEW_REQUIRED":
        return {
            "scheme": scheme,
            "source_identifier": source_id,
            "classification": "REVIEW_REQUIRED",
            "listing_hash": listing_hash,
            "document_hash": (
                previous_state.document_hash if previous_state else None
            ),
            "content_hash": (
                previous_state.content_hash if previous_state else None
            ),
            "dataset_fields": (
                previous_state.dataset_fields if previous_state else {}
            ),
            "source_text": previous_state.source_text if previous_state else "",
            "extraction_status": "review_required",
            "error": None,
            "resolved_guideline_url": (
                previous_state.resolved_guideline_url
                if previous_state
                else guideline_url
            ),
            "application_status": (
                previous_state.application_status if previous_state else "unknown"
            ),
            "application_deadline": (
                previous_state.application_deadline if previous_state else None
            ),
            "deadline_evidence": (
                previous_state.deadline_evidence if previous_state else None
            ),
        }

    if _is_placeholder_guideline_url(guideline_url):
        logger.warning(
            "Skipping unavailable official guideline URL for %s: %r",
            scheme.get("scholarship_name", "Unknown scholarship"),
            guideline_url,
        )
        if previous_state and previous_state.document_hash:
            logger.warning(
                "The previously linked guideline is no longer available for %s",
                scheme.get("scholarship_name", "Unknown scholarship"),
            )
            return {
                "scheme": scheme,
                "source_identifier": source_id,
                "classification": "REVIEW_REQUIRED",
                "listing_hash": listing_hash,
                "document_hash": previous_state.document_hash,
                "content_hash": previous_state.content_hash,
                "dataset_fields": previous_state.dataset_fields or {},
                "source_text": previous_state.source_text or "",
                "extraction_status": "review_required",
                "error": "Previously linked official guideline is no longer available.",
                "resolved_guideline_url": previous_state.resolved_guideline_url,
                "application_status": previous_state.application_status,
                "application_deadline": previous_state.application_deadline,
                "deadline_evidence": previous_state.deadline_evidence,
            }
    else:
        if not is_approved_https_url(guideline_url, source_key=source_key):
            raise ValueError("Guideline URL is outside the approved HTTPS domains.")
        validators = (
            {
                "etag": previous_state.etag,
                "last_modified": previous_state.last_modified,
            }
            if previous_same_guideline
            else None
        )
        if GUIDELINE_REQUEST_INTERVAL_SECONDS:
            time.sleep(GUIDELINE_REQUEST_INTERVAL_SECONDS)
        content, content_type, final_url, etag, last_modified = (
            _fetch_resource_details(
                guideline_url,
                validators=validators,
                source_key=source_key,
            )
        )
        if not is_approved_https_url(final_url, source_key=source_key):
            raise ValueError("Guideline redirect is outside the approved HTTPS domains.")
        resolved_guideline_url = final_url
        if not content and previous_same_guideline:
            document_hash = previous_state.document_hash
            guideline_text = previous_state.source_text or ""
            document_unchanged = True
        else:
            document_hash = sha256(content).hexdigest()
            guideline_fields, guideline_text, was_truncated = (
                _extract_guideline_document(content, content_type)
            )
            if not guideline_text:
                raise ValueError(
                    "Official guideline contains no extractable text; OCR is unavailable."
                )
            document_unchanged = bool(
                previous_state
                and previous_state.source_text == guideline_text
            )

    if not scheme.get("application_deadline"):
        scheme["application_deadline"] = (
            guideline_fields.get("application_deadline")
            or (
                previous_state.application_deadline
                if previous_state is not None
                else None
            )
        )
    if scheme.get("application_status", "unknown") == "unknown":
        if guideline_fields.get("application_status"):
            scheme["application_status"] = guideline_fields["application_status"]
        elif (
            previous_state is not None
            and previous_state.application_status in {"open", "closed"}
        ):
            scheme["application_status"] = previous_state.application_status
    deadline_evidence = (
        scheme.get("deadline_evidence")
        or guideline_fields.get("deadline_evidence")
        or (
            previous_state.deadline_evidence
            if previous_state is not None
            else None
        )
    )
    previous_evidence = (
        previous_state.deadline_evidence
        if previous_state is not None
        else ""
    )
    previous_start_date, previous_start_evidence = (
        _extract_document_application_start(previous_evidence or "")
    )
    application_start_date = (
        scheme.get("application_start_date")
        or guideline_fields.get("application_start_date")
        or previous_start_date
    )
    application_start_evidence = (
        scheme.get("application_start_evidence")
        or guideline_fields.get("application_start_evidence")
        or previous_start_evidence
    )
    period_evidence = list(
        dict.fromkeys(
            evidence_line
            for evidence in (application_start_evidence, deadline_evidence)
            if evidence
            for evidence_line in evidence.splitlines()
            if evidence_line.strip()
        )
    )
    deadline_evidence = "\n".join(period_evidence) or None

    source_text = "\n\n".join(
        part
        for part in (scheme.get("listing_text") or "", guideline_text)
        if part
    )
    if document_unchanged and previous_state and previous_state.dataset_fields:
        dataset_fields = {
            column: previous_state.dataset_fields.get(column)
            for column in DATASET_COLUMNS
        }
        deterministic_fields = _dataset_fields_from_sources(
            scheme,
            {},
            scheme.get("listing_text") or "",
        )
        for column, value in deterministic_fields.items():
            if value:
                dataset_fields[column] = value
    else:
        dataset_fields = _dataset_fields_from_sources(
            scheme,
            guideline_fields,
            guideline_text,
        )
        if previous_state and previous_state.dataset_fields:
            for column, value in previous_state.dataset_fields.items():
                if column in DATASET_COLUMNS and not dataset_fields.get(column) and value:
                    dataset_fields[column] = value

    content_hash = _content_hash(
        scheme,
        listing_hash,
        document_hash,
    )
    exact_same_content = bool(
        previous_state
        and previous_state.content_hash == content_hash
        and previous_state.dataset_fields
    )
    if exact_same_content:
        classification = "UNCHANGED" if has_source_record else "NEW"
        dataset_fields = {
            column: previous_state.dataset_fields.get(column)
            for column in DATASET_COLUMNS
        }
        extraction_status = previous_state.extraction_status
    else:
        classification = "UPDATED" if has_source_record else "NEW"
        extraction_status = "deterministic"
        ai_allowed = not document_unchanged and bool(source_text)
        if ai_allowed:
            dataset_fields = _extract_missing_fields_with_ai(
                dataset_fields,
                _ai_source_context(source_text),
                ai_client,
            )
            extraction_status = "ai_assisted" if ai_client else "deterministic"

    valid, validation_error = _validate_dataset_fields(
        dataset_fields,
        source_key=source_key,
    )
    if not valid:
        classification = "REVIEW_REQUIRED"
        extraction_status = "review_required"
        error = validation_error
    else:
        error = None
    substantive_columns = (
        "current_education",
        "eligible_castes_or_categories",
        "minimum_marks",
        "family_income_limit",
        "gender_restrictions",
        "benefits_provided",
        "key_documents_required",
    )
    if (
        classification in {"NEW", "UPDATED"}
        and not any(dataset_fields.get(column) for column in substantive_columns)
    ):
        classification = "REVIEW_REQUIRED"
        extraction_status = "review_required"
        error = "No substantive scholarship eligibility or benefit details were extracted."
    if was_truncated and classification in {"NEW", "UPDATED"}:
        classification = "REVIEW_REQUIRED"
        extraction_status = "review_required"
        error = "Guideline extraction was partial; manual review is required."

    if classification == "UNCHANGED" and previous_state:
        document_hash = previous_state.document_hash
        guideline_text = previous_state.source_text or ""
        etag = etag or previous_state.etag
        last_modified = last_modified or previous_state.last_modified

    return {
        "scheme": scheme,
        "source_identifier": source_id,
        "classification": classification,
        "listing_hash": listing_hash,
        "document_hash": document_hash,
        "content_hash": content_hash,
        "dataset_fields": dataset_fields,
        "source_text": guideline_text,
        "resolved_guideline_url": resolved_guideline_url,
        "guideline_fields": guideline_fields,
        "etag": etag,
        "last_modified": last_modified,
        "extraction_status": extraction_status,
        "error": error,
        "application_status": scheme.get("application_status", "unknown"),
        "application_start_date": application_start_date,
        "application_start_evidence": application_start_evidence,
        "application_deadline": scheme.get("application_deadline"),
        "deadline_evidence": deadline_evidence,
    }


def run_pipeline(
    discovery_only: bool = True,
    session_factory=None,
    source_key: str = "nsp",
    ai_client: Any = None,
) -> dict[str, Any]:
    make_session = session_factory or SessionLocal
    source = SOURCES.get(source_key)
    if source is None:
        raise ValueError(f"Unknown scholarship source: {source_key}")
    if source_key not in ENABLED_SOURCE_KEYS:
        raise ValueError(f"Scholarship source {source_key!r} is not enabled.")
    if source.adapter != "nsp":
        raise NotImplementedError(
            f"No ingestion adapter is implemented for source {source_key!r}."
        )

    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    with make_session() as db:
        Base.metadata.create_all(
            bind=db.get_bind(),
            tables=[
                ScholarshipIngestionSource.__table__,
                ScholarshipIngestionState.__table__,
                ScholarshipIngestionRun.__table__,
                ScholarshipIngestionEvent.__table__,
            ],
        )
        with db.begin():
            source_row = db.get(ScholarshipIngestionSource, source_key)
            if source_row is None:
                source_row = ScholarshipIngestionSource(
                    source_key=source.key,
                    name=source.name,
                    listing_url=source.listing_url,
                    enabled=source.enabled,
                    updated_at=started_at,
                )
                db.add(source_row)
            source_row.name = source.name
            source_row.listing_url = source.listing_url
            source_row.enabled = source.enabled
            source_row.last_started_at = started_at
            source_row.last_error = None
            source_row.updated_at = started_at
            db.add(
                ScholarshipIngestionRun(
                    id=run_id,
                    source_key=source_key,
                    source_url=source.listing_url,
                    started_at=started_at,
                    status="running",
                    statistics={},
                )
            )

    def mark_run_failed(error: Exception) -> None:
        failed_at = datetime.now(timezone.utc)
        with make_session() as db:
            with db.begin():
                run = db.get(ScholarshipIngestionRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.completed_at = failed_at
                    run.error = str(error)
                source_row = db.get(ScholarshipIngestionSource, source_key)
                if source_row is not None:
                    source_row.last_error = str(error)
                    source_row.updated_at = failed_at

    logger.info("Fetching scholarship listing from %s", source.listing_url)
    try:
        schemes = extract_schemes(fetch_page())
        if not schemes:
            raise RuntimeError(
                "No schemes were extracted. The official page structure may have changed."
            )
    except Exception as exc:
        logger.exception("Could not fetch or parse source %s", source_key)
        mark_run_failed(exc)
        raise

    with make_session() as db:
        existing = _load_existing_records(db)
        previous_states = {
            state.source_identifier: state
            for state in db.query(ScholarshipIngestionState)
            .filter(ScholarshipIngestionState.source_key == source_key)
            .all()
        }
    _, fuzzy_reviews, exact_matches = _classify_schemes(schemes, existing)
    exact_by_source = {
        _source_identifier(item["scheme"]): item
        for item in exact_matches
        if item.get("action") in {"update", "exact_existing"}
    }
    fuzzy_by_source = {
        _source_identifier(item["scheme"]): item
        for item in fuzzy_reviews
    }
    if ai_client is None:
        ai_client = _create_groq_client()

    processed: list[dict[str, Any]] = []
    skipped = 0
    seen: set[str] = set()
    for scheme in schemes:
        source_id = _source_identifier(scheme)
        if source_id in seen:
            skipped += 1
            continue
        seen.add(source_id)

        match = exact_by_source.get(source_id)
        review = fuzzy_by_source.get(source_id)
        if review or (match and match.get("action") != "update"):
            possible_matches = (
                review.get("possible_matches", [])
                if review
                else [
                    {
                        "matched_name": match.get("matched_name"),
                        "similarity": 1.0,
                    }
                ]
            )
            result = {
                "scheme": scheme,
                "source_identifier": source_id,
                "classification": "REVIEW_REQUIRED",
                "listing_hash": _listing_hash(scheme),
                "document_hash": (
                    previous_states[source_id].document_hash
                    if source_id in previous_states
                    else None
                ),
                "content_hash": (
                    previous_states[source_id].content_hash
                    if source_id in previous_states
                    else None
                ),
                "dataset_fields": (
                    previous_states[source_id].dataset_fields
                    if source_id in previous_states
                    else {}
                ),
                "source_text": (
                    previous_states[source_id].source_text
                    if source_id in previous_states
                    else ""
                ),
                "resolved_guideline_url": (
                    previous_states[source_id].resolved_guideline_url
                    if source_id in previous_states
                    else scheme.get("scheme_info_link")
                ),
                "extraction_status": "review_required",
                "error": None,
                "application_status": (
                    previous_states[source_id].application_status
                    if source_id in previous_states
                    else scheme.get("application_status", "unknown")
                ),
                "application_deadline": (
                    previous_states[source_id].application_deadline
                    if source_id in previous_states
                    else scheme.get("application_deadline")
                ),
                "deadline_evidence": (
                    previous_states[source_id].deadline_evidence
                    if source_id in previous_states
                    else scheme.get("deadline_evidence")
                ),
                "possible_matches": possible_matches,
            }
        else:
            has_source_record = bool(match and match.get("action") == "update")
            base_classification = (
                "UPDATED" if has_source_record else "NEW"
            )
            try:
                result = _process_incremental_scheme(
                    scheme,
                    previous_states.get(source_id),
                    has_source_record,
                    base_classification,
                    ai_client,
                    source_key=source_key,
                )
            except Exception as exc:
                logger.warning(
                    "Could not process scholarship %s; continuing with remaining source records",
                    scheme.get("scholarship_name", "Unknown scholarship"),
                    exc_info=True,
                )
                previous_state = previous_states.get(source_id)
                result = {
                    "scheme": scheme,
                    "source_identifier": source_id,
                    "classification": "FAILED",
                    "listing_hash": _listing_hash(scheme),
                    "document_hash": (
                        previous_state.document_hash if previous_state else None
                    ),
                    "content_hash": (
                        previous_state.content_hash if previous_state else None
                    ),
                    "dataset_fields": (
                        previous_state.dataset_fields if previous_state else {}
                    ),
                    "source_text": (
                        previous_state.source_text if previous_state else ""
                    ),
                    "resolved_guideline_url": (
                        previous_state.resolved_guideline_url
                        if previous_state
                        else scheme.get("scheme_info_link")
                    ),
                    "extraction_status": "failed",
                    "error": str(exc),
                    "application_status": (
                        previous_state.application_status
                        if previous_state
                        else "unknown"
                    ),
                    "application_deadline": (
                        previous_state.application_deadline
                        if previous_state
                        else None
                    ),
                    "deadline_evidence": (
                        previous_state.deadline_evidence if previous_state else None
                    ),
                }
        processed.append(result)

    classification_counts = {
        classification: sum(
            result["classification"] == classification for result in processed
        )
        for classification in CONTENT_CLASSIFICATIONS
    }
    classification_counts["SKIPPED"] = skipped
    classification_counts["INVALID"] = sum(
        result["classification"] == "REVIEW_REQUIRED"
        and bool(result.get("error"))
        for result in processed
    )
    persist_stats = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "skipped": skipped,
        "invalid": classification_counts["INVALID"],
    }
    hash_history: dict[str, dict[str, dict[str, str | None]]] = {}
    application_periods: dict[str, dict[str, str | None]] = {}
    for result in processed:
        previous_state = previous_states.get(result["source_identifier"])
        hash_history[result["source_identifier"]] = {
            "previous": {
                "listing": previous_state.listing_hash if previous_state else None,
                "document": previous_state.document_hash if previous_state else None,
                "content": previous_state.content_hash if previous_state else None,
            },
            "current": {
                "listing": result.get("listing_hash"),
                "document": result.get("document_hash"),
                "content": result.get("content_hash"),
            },
        }
        previous_evidence = (
            previous_state.deadline_evidence
            if previous_state is not None
            else ""
        )
        previous_start_date, _ = _extract_document_application_start(
            previous_evidence or ""
        )
        application_periods[result["source_identifier"]] = {
            "start": (
                result.get("application_start_date")
                or result["scheme"].get("application_start_date")
                or previous_start_date
            ),
            "end": (
                result.get("application_deadline")
                or result["scheme"].get("application_deadline")
                or (
                    previous_state.application_deadline
                    if previous_state is not None
                    else None
                )
            ),
            "status": result.get(
                "application_status",
                result["scheme"].get("application_status", "unknown"),
            ),
            "evidence": (
                result.get("deadline_evidence")
                or result["scheme"].get("deadline_evidence")
                or (
                    previous_state.deadline_evidence
                    if previous_state is not None
                    else None
                )
            ),
        }
    timestamp = datetime.now(timezone.utc)
    final_record_count = 0
    try:
        with make_session() as db:
            with db.begin():
                run = db.get(ScholarshipIngestionRun, run_id)
                if run is None:
                    raise RuntimeError("The ingestion run record disappeared.")
                if db.get_bind().dialect.name == "postgresql":
                    db.execute(
                        text(
                            "SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"
                        ),
                        {"lock_key": f"scholarship-ingestion:{source_key}"},
                    )
                for result in processed:
                    source_id = result["source_identifier"]
                    previous_state = db.get(
                        ScholarshipIngestionState,
                        {
                            "source_key": source_key,
                            "source_identifier": source_id,
                        },
                    )
                    classification = result["classification"]
                    if previous_state is None:
                        previous_state = ScholarshipIngestionState(
                            source_key=source_key,
                            source_identifier=source_id,
                            last_seen_at=timestamp,
                        )
                        db.add(previous_state)
                    previous_state.last_seen_at = timestamp
                    previous_state.classification = classification
                    previous_state.extraction_status = result.get(
                        "extraction_status", "pending"
                    )
                    previous_state.last_error = result.get("error")
                    previous_state.source_url = source.listing_url
                    previous_state.guideline_url = result["scheme"].get(
                        "scheme_info_link"
                    )
                    previous_state.resolved_guideline_url = result.get(
                        "resolved_guideline_url"
                    )
                    previous_state.listing_hash = result.get("listing_hash")
                    if classification != "FAILED":
                        if "scholarship_id" in result:
                            previous_state.scholarship_id = result["scholarship_id"]
                        previous_state.document_hash = result.get("document_hash")
                        previous_state.content_hash = result.get("content_hash")
                        previous_state.etag = result.get("etag")
                        previous_state.last_modified = result.get("last_modified")
                        previous_state.dataset_fields = result.get(
                            "dataset_fields", {}
                        )
                        previous_state.source_text = result.get("source_text", "")
                        previous_state.application_status = result.get(
                            "application_status", "unknown"
                        )
                        previous_state.application_deadline = result.get(
                            "application_deadline"
                        )
                        previous_state.deadline_evidence = result.get(
                            "deadline_evidence"
                        )
                        previous_state.last_extracted_at = (
                            timestamp
                            if result.get("extraction_status") in {
                                "deterministic",
                                "ai_assisted",
                            }
                            else previous_state.last_extracted_at
                        )

                    if (
                        not discovery_only
                        and classification in {"NEW", "UPDATED"}
                    ):
                        scheme = result["scheme"]
                        scheme["_dataset_fields"] = result["dataset_fields"]
                        scheme["_guideline_fields"] = result.get(
                            "guideline_fields", {}
                        )
                        record = _record_from_scheme(scheme)
                        status = result.get("application_status", "unknown")
                        record["active_status"] = (
                            status if status in {"open", "closed"} else "unknown"
                        )
                        deadline = _parse_deadline(
                            result.get("application_deadline")
                        )
                        record["is_active"] = bool(
                            status == "open"
                            and deadline
                            and deadline.date() >= timestamp.date()
                        )
                        source_match = next(
                            (
                                row
                                for row in _load_existing_records(db)
                                if SOURCE_FILENAME in _tokens(row.get("source_filename"))
                                and source_id in _tokens(
                                    row.get("source_identifier")
                                )
                            ),
                            None,
                        )
                        if source_match:
                            scholarship = db.get(Scholarship, source_match["id"])
                            if scholarship is None:
                                raise RuntimeError(
                                    "NSP source match disappeared during persistence."
                                )
                            changed = _apply_scheme_update(scholarship, record)
                            if scholarship.active_status != record["active_status"]:
                                scholarship.active_status = record["active_status"]
                                changed = True
                            if scholarship.is_active != record["is_active"]:
                                scholarship.is_active = record["is_active"]
                                changed = True
                            result["scholarship_id"] = scholarship.id
                            persist_stats["updated" if changed else "unchanged"] += 1
                        else:
                            scholarship = Scholarship(**record)
                            scholarship.active_status = record["active_status"]
                            scholarship.is_active = record["is_active"]
                            db.add(scholarship)
                            db.flush()
                            result["scholarship_id"] = scholarship.id
                            persist_stats["inserted"] += 1
                        previous_state.scholarship_id = result["scholarship_id"]
                        db.flush()

                    db.add(
                        ScholarshipIngestionEvent(
                            id=str(uuid4()),
                            run_id=run_id,
                            source_key=source_key,
                            source_identifier=source_id,
                            scholarship_id=result.get("scholarship_id"),
                            classification=classification,
                            source_url=source.listing_url,
                            guideline_url=result["scheme"].get("scheme_info_link"),
                            resolved_guideline_url=result.get(
                                "resolved_guideline_url"
                            ),
                            listing_hash=result.get("listing_hash"),
                            document_hash=result.get("document_hash"),
                            extracted_fields=result.get("dataset_fields", {}),
                            error=result.get("error"),
                            created_at=timestamp,
                        )
                    )

                failure_messages = [
                    result["error"]
                    for result in processed
                    if result.get("error")
                ]
                source_row = db.get(ScholarshipIngestionSource, source_key)
                if source_row is None:
                    raise RuntimeError("The ingestion source record disappeared.")
                source_row.last_success_at = timestamp
                source_row.last_error = (
                    "; ".join(failure_messages[:5]) if failure_messages else None
                )
                source_row.updated_at = timestamp
                run.completed_at = timestamp
                run.status = (
                    "completed_with_errors"
                    if failure_messages
                    else "completed"
                )
                db.flush()
                final_record_count = db.query(Scholarship).count()
                run.statistics = {
                    **classification_counts,
                    **persist_stats,
                    "discovered": len(schemes),
                    "final_record_count": final_record_count,
                    "hashes": hash_history,
                    "application_periods": application_periods,
                }
    except Exception as exc:
        logger.exception(
            "Scholarship ingestion transaction failed; all scholarship and trace writes rolled back"
        )
        mark_run_failed(exc)
        raise

    new_results = [
        result for result in processed if result["classification"] == "NEW"
    ]
    review_results = [
        result
        for result in processed
        if result["classification"] == "REVIEW_REQUIRED"
    ]
    failed_results = [
        result for result in processed if result["classification"] == "FAILED"
    ]
    report: dict[str, Any] = {
        "source": source_key,
        "run_id": run_id,
        "extracted": len(schemes),
        "discovered": len(schemes),
        "existing_records": len(existing),
        "exact_matches": len(exact_matches),
        "possible_duplicates": len(review_results),
        "potential_new": len(new_results),
        "discovery_only": discovery_only,
        "classifications": [
            {
                "scholarship_name": result["scheme"].get("scholarship_name"),
                "source_identifier": result["source_identifier"],
                "classification": result["classification"],
                "source_url": source.listing_url,
                "guideline_url": result["scheme"].get("scheme_info_link"),
                "document_hash": result.get("document_hash"),
                "application_period": application_periods[
                    result["source_identifier"]
                ],
                "error": result.get("error"),
            }
            for result in processed
        ],
        "new_schemes": [
            {
                "scheme": result["scheme"],
                "dataset_fields": result["dataset_fields"],
            }
            for result in new_results
        ],
        "review_schemes": review_results,
        "failed_schemes": failed_results,
        "exact_match_details": exact_matches,
        "inserted": persist_stats["inserted"],
        "updated": persist_stats["updated"],
        "unchanged": classification_counts["UNCHANGED"],
        "skipped": skipped,
        "invalid": classification_counts["INVALID"],
        "statistics": {
            **classification_counts,
            **persist_stats,
            "discovered": len(schemes),
            "failed": len(failed_results),
            "final_record_count": final_record_count,
            "hashes": hash_history,
            "application_periods": application_periods,
        },
    }
    logger.info(
        "Scholarship pipeline summary: source=%s extracted=%s existing=%s new=%s "
        "updated=%s unchanged=%s review_required=%s failed=%s inserted=%s "
        "skipped=%s discovery_only=%s",
        source_key,
        report["extracted"],
        report["existing_records"],
        len(new_results),
        report["updated"],
        report["unchanged"],
        len(review_results),
        len(failed_results),
        report["inserted"],
        report["skipped"],
        report["discovery_only"],
    )
    return report


def run_scheduler(
    discovery_only: bool = True,
    stop_event: Event | None = None,
) -> None:
    stop = stop_event or Event()
    logger.info(
        "Starting scholarship scheduler with a %s-hour interval (discovery_only=%s)",
        SCHEDULE_INTERVAL_SECONDS // 3600,
        discovery_only,
    )
    while not stop.is_set():
        for source in enabled_sources():
            try:
                run_pipeline(
                    discovery_only=discovery_only,
                    source_key=source.key,
                )
            except Exception:
                logger.exception(
                    "Scheduled source %s run failed; the next run remains scheduled",
                    source.key,
                )
        if stop.wait(SCHEDULE_INTERVAL_SECONDS):
            break


def run_discovery() -> dict[str, Any]:
    return run_pipeline(discovery_only=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and classify scholarships from the National Scholarship Portal."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--discovery-only",
        dest="discovery_only",
        action="store_true",
        help=(
            "Classify and record source history without inserting or updating "
            "Scholarship rows (default)."
        ),
    )
    mode.add_argument(
        "--persist",
        dest="discovery_only",
        action="store_false",
        help=(
            "Persist validated NEW/UPDATED records; update only scholarships "
            "previously sourced from the selected source."
        ),
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run immediately, then repeat every 24 hours.",
    )
    parser.add_argument(
        "--source",
        choices=sorted(SOURCES),
        default="nsp",
        help="Select an allowlisted source; disabled sources are rejected.",
    )
    parser.set_defaults(discovery_only=True)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.schedule:
        try:
            run_scheduler(discovery_only=args.discovery_only)
        except KeyboardInterrupt:
            logger.info("NSP scheduler stopped")
    else:
        try:
            report = run_pipeline(
                discovery_only=args.discovery_only,
                source_key=args.source,
            )
            print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
        except Exception:
            logger.exception("NSP fetch pipeline failed")
            raise


if __name__ == "__main__":
    main()
