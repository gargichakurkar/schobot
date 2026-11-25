"""Explicitly replace the scholarship catalogue from the dual-links CSV."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from app.core.database import SessionLocal, engine
from app.models import (
    ReminderEvent,
    ReminderPreference,
    ScholarshipMatch,
    StudentScholarshipDocument,
    StudentScholarshipProgress,
)
from app.models.scholarship import Scholarship
from app.seed.import_scholarships import DUAL_FILENAME, DATA_DIRECTORY, import_scholarship_datasets


CONFIRMATION = "RESET-SCHOLARSHIPS"
RELATED_MODELS = (
    ("scholarship_matches", ScholarshipMatch),
    ("student_scholarship_progress", StudentScholarshipProgress),
    ("student_scholarship_documents", StudentScholarshipDocument),
    ("reminder_events", ReminderEvent),
    ("reminder_preferences", ReminderPreference),
    ("scholarships", Scholarship),
)


def reset_and_import_in_transaction(db, source: Path) -> dict:
    """Replace scholarship data atomically; callers must back up before calling."""
    db.info["scholar_import_commit"] = False
    with db.begin():
        for _, model in RELATED_MODELS:
            db.query(model).delete(synchronize_session=False)
        report = import_scholarship_datasets(db, source)
        stats = (
            report.get(source.name)
            or report.get(DUAL_FILENAME)
            or report.get("scholarships_dataset_dual_links.csv")
            or next(v for k, v in report.items() if isinstance(v, dict))
        )
        processed = sum(
            stats[key]
            for key in ("inserted", "updated", "unchanged", "skipped", "invalid")
        )
        if processed != stats["rows"]:
            raise RuntimeError(
                f"Import validation failed: processed {processed} of {stats['rows']} source rows."
            )
        if stats["invalid"]:
            raise RuntimeError(
                f"Import validation failed: {stats['invalid']} dual-links rows were invalid."
            )
        if report["unique_records"] != stats["inserted"]:
            raise RuntimeError(
                "Import validation failed: scholarship table count does not match inserted source rows."
            )
    return report


def sqlite_database_path() -> Path:
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("A SQLite database is required to create the pre-reset backup.")
    raw_path = engine.url.database
    if not raw_path or raw_path == ":memory:":
        raise RuntimeError("A file-backed SQLite database is required for the pre-reset backup.")
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()


def make_backup(database_path: Path) -> Path:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    backup_path = database_path.with_name(f"{database_path.stem}.pre-scholarship-reset-{stamp}{database_path.suffix}")
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    return backup_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete scholarship catalogue and related student scholarship records, then import only the dual-links dataset."
    )
    parser.add_argument(
        "--confirm",
        metavar="RESET-SCHOLARSHIPS",
        help="Required exact confirmation phrase: RESET-SCHOLARSHIPS",
    )
    args = parser.parse_args()

    source = DATA_DIRECTORY / DUAL_FILENAME
    if not source.is_file():
        raise FileNotFoundError(f"Dual-links scholarship source is missing: {source}")

    with SessionLocal() as db:
        counts = {name: db.query(model).count() for name, model in RELATED_MODELS}

    print("WARNING: this operation replaces the scholarship catalogue.")
    print(f"Source: {source}")
    print("Rows to delete: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    print("Match, progress, scholarship document, and scholarship reminder rows will be deleted; student profiles and unrelated data will remain.")
    if args.confirm != CONFIRMATION:
        print(f"No changes made. Re-run with --confirm {CONFIRMATION} to continue.")
        raise SystemExit(2)

    database_path = sqlite_database_path()
    backup_path = make_backup(database_path)
    print(f"SQLite backup created: {backup_path}")

    try:
        with SessionLocal() as db:
            report = reset_and_import_in_transaction(db, source)
    except Exception:
        print(f"Import failed; the pre-reset backup is available at: {backup_path}")
        raise

    print(f"Imported from {DUAL_FILENAME}: {report[DUAL_FILENAME]}")
    print(f"Scholarship rows after reseed: {report['unique_records']}")


if __name__ == "__main__":
    main()
