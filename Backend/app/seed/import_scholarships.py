from __future__ import annotations

import argparse
import csv
import hashlib
from io import StringIO
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine
from app.core.migrations import migrate_scholarship_columns
from app.models import Scholarship


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIRECTORY = PROJECT_ROOT / "data"
LEGACY_FILENAME = "scholar.csv"  # retained only to recognize existing provenance
DUAL_FILENAME = "scholarships_dataset_dual_links (Autosaved).csv"
STAT_NAMES = ("rows", "inserted", "updated", "unchanged", "skipped", "invalid")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalize_text(value).casefold()).strip()


def _display_category(value: str) -> str | None:
    category = normalize_text(value)
    if not category:
        return None
    if re.fullmatch(r"(?:all|all categories|open to all categories)", category, re.I):
        return "All Categories"
    if category.casefold() == "open":
        return "General"
    if re.fullmatch(r"open to all categories\s*\(.*\)", category, re.I):
        return "All Categories"

    display = category.title()
    for abbreviation in (
        "DNT",
        "EBC",
        "EWS",
        "NTDNT",
        "OBC",
        "PWD",
        "SBC",
        "SC",
        "SEBC",
        "ST",
        "VJNT",
    ):
        display = re.sub(rf"\b{abbreviation.title()}\b", abbreviation, display)
    display = re.sub(r"\bSc/St\b", "SC/ST", display)
    display = re.sub(r"\bSc Or Nb\b", "SC Or NB", display)
    display = re.sub(r"\bVj Or Nt Or Sbc\b", "VJ Or NT Or SBC", display)
    return display


def _normalize_state(value: str) -> str | None:
    state = normalize_text(value)
    if not state:
        return None
    if state.casefold() in {"all india", "india", "pan india", "nationwide"}:
        return "All India"
    return state.title()


def _education_labels(value: str) -> set[str]:
    text = normalize_text(value).casefold().replace("–", "-").replace("—", "-")
    labels: set[str] = set()
    if re.search(r"(?:1st|class\s*1)\s*(?:to|-)\s*(?:10th|class\s*10)", text):
        labels.update({"Class 9", "Class 10"})
    if re.search(
        r"(?:class(?:es)?\s*)?11\s*(?:and|&|or|-)\s*(?:class(?:es)?\s*)?12|11th\s*(?:and|&|or)\s*12th",
        text,
    ):
        labels.update({"Class 11", "Class 12"})
    else:
        if re.search(r"\b(?:class\s*11|11th|fyjc|syjc)\b", text):
            labels.add("Class 11")
        if re.search(r"\b(?:class\s*12|12th|hsc)\b", text):
            labels.add("Class 12")
    if re.search(
        r"\b(?:undergraduate|under[\s-]?graduation|undergrad|graduat(?:ion)?|graduate|bachelor|degree|b\.?\s?tech|bsc)\b",
        text,
    ):
        labels.add("Undergraduate")
    if re.search(
        r"\b(?:postgraduate|post[\s-]?graduation|postgrad|master|ph\.?\s?d|doctorate|doctor)\b",
        text,
    ):
        labels.add("Postgraduate")
    if re.search(r"\b(?:diploma|polytechnic)\b", text):
        labels.add("Diploma")
    return labels


def _income_limit(value: str) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    if re.search(r"\b(?:monthly|per\s+month|month)\b", text, re.I):
        return None
    match = re.search(
        r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>crore|crores|lakh|lakhs|lac|lacs|thousand|k)?",
        text,
        re.I,
    )
    if not match:
        return None
    number = float(match.group("number").replace(",", ""))
    unit = (match.group("unit") or "").casefold()
    multiplier = (
        10_000_000
        if unit.startswith("crore")
        else 100_000
        if unit.startswith(("lakh", "lac"))
        else 1_000
        if unit in {"thousand", "k"}
        else 1
    )
    amount = number * multiplier
    return amount if amount > 0 else None


def _percentage(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", normalize_text(value))
    return float(match.group(1)) if match else None


def _year_from_description(value: str) -> str | None:
    match = re.search(r"\b(?:19|20)\d{2}(?:\s*[-/–]\s*(?:\d{2}|\d{4}))?\b", value)
    return normalize_text(match.group(0)) if match else None


def _source_key(source_filename: str, identifier: str) -> str:
    return f"{source_filename.casefold()}::{normalize_key(identifier)}"


def _dual_identifier(name: str, provider: str, category: str, link: str) -> str:
    components = (
        normalize_key(name),
        normalize_key(provider),
        normalize_key(category),
        normalize_key(link),
    )
    digest = hashlib.sha256("|".join(components).encode("utf-8")).hexdigest()[:20]
    return f"dual:{digest}"


def map_dual_row(row: dict[str, str]) -> dict[str, Any]:
    name = normalize_text(row.get("scholarship_name"))
    if not name:
        raise ValueError(f"{DUAL_FILENAME} row has no scholarship name")

    provider = normalize_text(row.get("offered_by")) or None
    education = normalize_text(row.get("current_education")) or None
    categories = normalize_text(row.get("eligible_castes_or_categories"))
    income_text = normalize_text(row.get("family_income_limit")) or None
    marks_text = normalize_text(row.get("minimum_marks")) or None
    gender_text = normalize_text(row.get("gender_restrictions")) or None
    identifier = _dual_identifier(
        name,
        provider or "",
        categories,
        normalize_text(row.get("official_portal_link")),
    )
    gender_requirement = None
    if gender_text and re.search(r"\b(?:female|girls?|women)\b", gender_text, re.I):
        if re.search(r"\b(?:only|exclusively)\b", gender_text, re.I):
            gender_requirement = "Female"
    elif gender_text and re.search(r"\b(?:male|boys?|men)\b", gender_text, re.I):
        if re.search(r"\b(?:only|exclusively)\b", gender_text, re.I):
            gender_requirement = "Male"

    details = []
    if categories:
        details.append(f"Eligible categories/communities: {categories}")
    if marks_text:
        details.append(f"Minimum marks: {marks_text}")
    if gender_text:
        details.append(f"Gender restrictions: {gender_text}")

    return {
        "dataset_id": _source_key(DUAL_FILENAME, identifier),
        "scholarship_name": name,
        "provider": provider,
        "scholarship_type": normalize_text(row.get("Type")) or None,
        "state": normalize_text(row.get("State")) or None,
        "category": _display_category(categories),
        "income_text": income_text,
        "max_income": _income_limit(income_text or ""),
        "qualification_text": education,
        "eligible_level": education,
        "benefits": normalize_text(row.get("benefits_provided")) or None,
        "required_documents": normalize_text(row.get("key_documents_required")) or None,
        "eligibility_details": "\n".join(details) or None,
        "official_link": normalize_text(row.get("official_portal_link")) or None,
        "scheme_info_link": normalize_text(row.get("scheme_info_link")) or None,
        "minimum_marks_text": marks_text,
        "min_percentage": _percentage(marks_text or ""),
        "gender_requirement": gender_requirement,
        "source_filename": DUAL_FILENAME,
        "source_identifier": identifier,
        "active_status": "unknown",
        "is_active": False,
    }


def _tokens(value: str | None) -> set[str]:
    return {token.strip() for token in (value or "").split(";") if token.strip()}


def _eligibility_detail_lines(value: str | None) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    labels = (
        "Additional education requirements",
        "Additional eligible categories/communities",
        "Additional income criterion",
        "Eligible categories/communities",
        "Gender restrictions",
        "Minimum marks",
    )
    label_pattern = "|".join(re.escape(label) for label in labels)
    parts = re.split(rf"(?=(?:{label_pattern}):)", text)
    return {part.strip() for part in parts if part.strip()}


def _merge_source_metadata(scholarship: Scholarship, record: dict[str, Any]) -> bool:
    changed = False
    for field in ("source_filename", "source_identifier"):
        existing_tokens = _tokens(getattr(scholarship, field))
        incoming_tokens = _tokens(record.get(field))
        combined = existing_tokens | incoming_tokens
        value = "; ".join(sorted(combined))
        if value != getattr(scholarship, field):
            setattr(scholarship, field, value)
            changed = True
    return changed


def _append_additional_category(scholarship: Scholarship, category: str) -> bool:
    current = _tokens(scholarship.additional_category_requirements)
    incoming = normalize_text(category)
    if not incoming or incoming in current:
        return False
    current.add(incoming)
    scholarship.additional_category_requirements = "; ".join(sorted(current))

    detail = f"Additional eligible categories/communities: {incoming}"
    details = _eligibility_detail_lines(scholarship.eligibility_details)
    if detail not in details:
        details.add(detail)
        scholarship.eligibility_details = "\n".join(
            sorted(details)
        )
    return True


def _append_additional_education(scholarship: Scholarship, education: str) -> bool:
    current = _tokens(scholarship.additional_education_requirements)
    incoming = normalize_text(education)
    if not incoming or incoming in current:
        return False
    current.add(incoming)
    scholarship.additional_education_requirements = "; ".join(sorted(current))

    detail = f"Additional education requirements: {incoming}"
    details = _eligibility_detail_lines(scholarship.eligibility_details)
    if detail not in details:
        details.add(detail)
        scholarship.eligibility_details = "\n".join(
            sorted(details)
        )
    return True


def _append_additional_income(scholarship: Scholarship, income: str) -> bool:
    current = _tokens(scholarship.additional_income_requirements)
    incoming = normalize_text(income)
    if not incoming or incoming in current:
        return False
    current.add(incoming)
    scholarship.additional_income_requirements = "; ".join(sorted(current))

    detail = f"Additional income criterion: {incoming}"
    details = _eligibility_detail_lines(scholarship.eligibility_details)
    if detail not in details:
        details.add(detail)
        scholarship.eligibility_details = "\n".join(sorted(details))
    return True


def _categories_compatible(existing: str | None, incoming: str | None) -> bool:
    existing_key = normalize_key(existing)
    incoming_key = normalize_key(incoming)
    if not existing_key or not incoming_key:
        return True
    if existing_key in {"all", "all categories"}:
        return True
    category_pattern = r"\b(?:sc|st|obc|sebc|general|open|ews|vjnt|dnt|ntdnt|sbc|pwd)\b"
    existing_terms = set(re.findall(category_pattern, existing_key))
    incoming_terms = set(re.findall(category_pattern, incoming_key))
    if existing_terms and incoming_terms:
        return bool(existing_terms & incoming_terms)
    return existing_key == incoming_key


def _find_cross_source_match(db: Session, record: dict[str, Any]) -> Scholarship | None:
    name_key = normalize_key(record["scholarship_name"])
    candidates = (
        db.query(Scholarship)
        .filter(Scholarship.state.ilike("All India"))
        .order_by(Scholarship.dataset_id, Scholarship.id)
        .all()
    )
    for candidate in candidates:
        if normalize_key(candidate.scholarship_name) != name_key:
            continue
        if normalize_text(candidate.official_link).casefold() != normalize_text(record.get("official_link")).casefold():
            continue
        if not _categories_compatible(candidate.category, record.get("category")):
            continue
        candidate_levels = _education_labels(candidate.qualification_text or candidate.eligible_level or "")
        incoming_levels = _education_labels(record.get("qualification_text") or "")
        if not candidate_levels or not incoming_levels or not candidate_levels.intersection(incoming_levels):
            continue
        return candidate
    return None


def _lookup_existing(
    db: Session,
    record: dict[str, Any],
    source_filename: str,
) -> Scholarship | None:
    identifier = record["source_identifier"]
    # Provenance tokens are the stable identity within each source. Dataset IDs
    # are retained for compatibility, but may differ after cross-source merges.
    possible_matches = (
        db.query(Scholarship)
        .filter(
            Scholarship.source_filename.ilike(f"%{source_filename}%"),
            Scholarship.source_identifier.ilike(f"%{identifier}%"),
        )
        .order_by(Scholarship.id)
        .all()
    )
    for candidate in possible_matches:
        if (
            source_filename in _tokens(candidate.source_filename)
            and identifier in _tokens(candidate.source_identifier)
        ):
            return candidate

    return None


def _apply_record(scholarship: Scholarship, record: dict[str, Any]) -> bool:
    changed = False
    existing_sources = _tokens(scholarship.source_filename)
    incoming_source = record.get("source_filename")
    is_cross_source = bool(existing_sources - {incoming_source})
    for field, value in record.items():
        if field == "_clear_zero_income":
            if value and normalize_key(scholarship.income_text) == "0":
                scholarship.income_text = None
                changed = True
            continue
        if field in {"source_filename", "source_identifier"}:
            continue
        if field == "dataset_id" and getattr(scholarship, field):
            continue
        if value is None or value == "":
            continue
        if field == "category" and is_cross_source and scholarship.category:
            if (
                incoming_source == LEGACY_FILENAME
                and DUAL_FILENAME in existing_sources
                and scholarship.category != value
            ):
                changed = _append_additional_category(scholarship, scholarship.category) or changed
                scholarship.category = value
                changed = True
            elif (
                incoming_source == DUAL_FILENAME
                and LEGACY_FILENAME in existing_sources
                and scholarship.category != value
            ):
                changed = _append_additional_category(scholarship, value) or changed
                continue
        if field in {"qualification_text", "eligible_level"} and is_cross_source:
            existing_education = getattr(scholarship, field)
            if existing_education and existing_education != value:
                if incoming_source == LEGACY_FILENAME and DUAL_FILENAME in existing_sources:
                    changed = _append_additional_education(
                        scholarship,
                        existing_education,
                    ) or changed
                elif incoming_source == DUAL_FILENAME and LEGACY_FILENAME in existing_sources:
                    changed = _append_additional_education(scholarship, value) or changed
                    continue
        if field == "income_text" and is_cross_source:
            existing_income = getattr(scholarship, field)
            if existing_income and existing_income != value:
                if incoming_source == LEGACY_FILENAME and DUAL_FILENAME in existing_sources:
                    changed = _append_additional_income(scholarship, existing_income) or changed
                elif incoming_source == DUAL_FILENAME and LEGACY_FILENAME in existing_sources:
                    changed = _append_additional_income(scholarship, value) or changed
                    continue
        if field == "max_income" and is_cross_source:
            existing_income = getattr(scholarship, field)
            if existing_income is not None and existing_income != value:
                if incoming_source == DUAL_FILENAME and LEGACY_FILENAME in existing_sources:
                    continue
        if field == "eligibility_details" and is_cross_source:
            combined_details = set(_eligibility_detail_lines(getattr(scholarship, field)))
            combined_details.update(_eligibility_detail_lines(value))
            merged_details = "\n".join(sorted(combined_details)) or None
            if merged_details != getattr(scholarship, field):
                setattr(scholarship, field, merged_details)
                changed = True
            continue
        if getattr(scholarship, field) != value:
            setattr(scholarship, field, value)
            changed = True
    return _merge_source_metadata(scholarship, record) or changed


def _read_csv(path: Path, required_columns: set[str]) -> list[dict[str, str]]:
    content = path.read_bytes()
    try:
        decoded_content = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded_content = content.decode("cp1252")

    reader = csv.DictReader(StringIO(decoded_content, newline=""))
    headers = {header.strip() for header in (reader.fieldnames or [])}
    missing_headers = required_columns - headers
    if missing_headers:
        raise ValueError(
            f"{path} is missing required columns: {', '.join(sorted(missing_headers))}"
        )
    return [
        {
            (key or "").strip(): normalize_text(value)
            for key, value in row.items()
            if key is not None
        }
        for row in reader
    ]


def _empty_stats(row_count: int) -> dict[str, int]:
    return {name: row_count if name == "rows" else 0 for name in STAT_NAMES}


def _import_source(
    db: Session,
    path: Path,
    source_filename: str,
    required_columns: set[str],
    mapper,
    dry_run: bool = False,
    preview: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    rows = _read_csv(path, required_columns)
    stats = _empty_stats(len(rows))
    seen_keys: set[str] = set()

    try:
        for row_number, row in enumerate(rows, start=1):
            name = normalize_text(row.get("scholarship_name"))
            try:
                record = mapper(row)
            except (TypeError, ValueError):
                stats["invalid"] += 1
                if preview is not None:
                    preview.append(
                        {
                            "row": row_number,
                            "scholarship_name": name,
                            "action": "invalid",
                        }
                    )
                continue

            row_key = _source_key(source_filename, record["source_identifier"])
            if row_key in seen_keys:
                stats["skipped"] += 1
                action = "skipped"
            else:
                seen_keys.add(row_key)
                scholarship = _lookup_existing(db, record, source_filename)
                if scholarship is None:
                    scholarship = Scholarship()
                    db.add(scholarship)
                    _apply_record(scholarship, record)
                    db.flush()
                    stats["inserted"] += 1
                    action = "inserted"
                elif _apply_record(scholarship, record):
                    stats["updated"] += 1
                    action = "updated"
                else:
                    stats["unchanged"] += 1
                    action = "unchanged"
            if preview is not None:
                preview.append(
                    {
                        "row": row_number,
                        "scholarship_name": name,
                        "action": action,
                    }
                )

        db.flush()
        if db.info.get("scholar_import_commit", True) and not dry_run:
            db.commit()
    except Exception:
        if dry_run or db.info.get("scholar_import_commit", True):
            db.rollback()
        raise
    return stats


def import_scholarship_datasets(
    db: Session,
    dual_path: Path = DATA_DIRECTORY / DUAL_FILENAME,
    dry_run: bool = False,
) -> dict[str, Any]:
    preview: list[dict[str, Any]] | None = [] if dry_run else None
    try:
        initial_record_count = db.query(Scholarship).count() if dry_run else None
        dual_stats = _import_source(
            db,
            dual_path,
            DUAL_FILENAME,
            {"scholarship_name", "offered_by"},
            map_dual_row,
            dry_run=dry_run,
            preview=preview,
        )
        final_record_count = (
            initial_record_count + dual_stats["inserted"]
            if initial_record_count is not None
            else db.query(Scholarship).count()
        )
        if dry_run:
            db.rollback()
        report = {
            DUAL_FILENAME: dual_stats,
            "unique_records": final_record_count,
            "final_record_count": final_record_count,
        }
        if preview is not None:
            report["preview"] = preview
        return report
    except Exception:
        if dry_run or db.info.get("scholar_import_commit", True):
            db.rollback()
        raise


def _backup_sqlite_database() -> Path:
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        raise RuntimeError("A file-backed SQLite database is required for a pre-import backup.")
    raw_path = Path(engine.url.database)
    database_path = raw_path.resolve() if raw_path.is_absolute() else (Path.cwd() / raw_path).resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"Configured SQLite database does not exist: {database_path}")
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup_path = database_path.with_name(
        f"{database_path.stem}.pre-scholarship-import-{stamp}{database_path.suffix}"
    )
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    print(f"Pre-import SQLite backup created: {backup_path}")
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Import scholarships from the dual-links dataset only.")
    parser.add_argument("--dual-csv", type=Path, default=DATA_DIRECTORY / DUAL_FILENAME)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview the import without committing changes.",
    )
    args = parser.parse_args()

    if not args.dry_run:
        if engine.url.get_backend_name() == "sqlite":
            _backup_sqlite_database()
        Base.metadata.create_all(bind=engine)
        migrate_scholarship_columns(engine)
    with SessionLocal() as db:
        report = import_scholarship_datasets(db, args.dual_csv, dry_run=args.dry_run)
    stats = report[DUAL_FILENAME]
    print(f"Source: {args.dual_csv}")
    print(f"Total rows: {stats['rows']}")
    for name in ("inserted", "updated", "unchanged", "skipped", "invalid"):
        print(f"{name.capitalize()}: {stats[name]}")
    print(f"Final record count: {report['final_record_count']}")
    if args.dry_run:
        print("Dry run complete; no changes committed.")
        print("Dry-run preview:")
        for item in report["preview"]:
            print(
                f"  Row {item['row']}: {item['action']} - "
                f"{item['scholarship_name'] or '(missing scholarship name)'}"
            )


if __name__ == "__main__":
    main()
