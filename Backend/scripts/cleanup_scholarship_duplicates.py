"""Dry-run by default; test-copy-only transactional scholarship deduplication."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from dry_run_scholarship_dedup import build_report


BACKEND_ROOT = Path(__file__).resolve().parents[1]
LIVE_DATABASE = (BACKEND_ROOT / "schobot.db").resolve()
TEST_COPY_ROOT = (BACKEND_ROOT / "reports" / "test-copies").resolve()
EXCLUDED_GROUP_148_IDS = {
    "7a76aa09-bd9f-419f-abd4-8b87219e3c1e",
    "3e1ca9c2-05e2-4fc4-9022-6c4b97c08e7d",
}
AUDIT_TABLES = {
    "scholarship_dedup_audit_runs",
    "scholarship_dedup_scholarship_before",
    "scholarship_dedup_match_before",
    "scholarship_dedup_source_identity",
    "scholarship_dedup_child_before",
}
CHILD_TABLES = {
    "student_scholarship_progress",
    "student_scholarship_documents",
    "reminder_preferences",
    "reminder_events",
}


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def open_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(path.resolve().as_posix(), safe='/:')}?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only = ON")
    return db


def open_writable(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.resolve())
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def require_test_copy(path: Path) -> Path:
    resolved = path.resolve()
    if resolved == LIVE_DATABASE:
        raise ValueError(f"Refusing to modify the live database: {LIVE_DATABASE}")
    try:
        resolved.relative_to(TEST_COPY_ROOT)
    except ValueError as error:
        raise ValueError(
            f"Mutations are restricted to test copies under {TEST_COPY_ROOT}"
        ) from error
    if not resolved.is_file():
        raise ValueError(f"Test-copy database does not exist: {resolved}")
    return resolved


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_audit_schema(db: sqlite3.Connection) -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS scholarship_dedup_audit_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            finished_at TEXT,
            group_count INTEGER NOT NULL,
            excluded_group_ids_json TEXT NOT NULL,
            before_counts_json TEXT NOT NULL,
            after_counts_json TEXT,
            before_hashes_json TEXT NOT NULL,
            validation_json TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scholarship_dedup_scholarship_before (
            run_id TEXT NOT NULL,
            group_number INTEGER NOT NULL,
            original_scholarship_id TEXT NOT NULL,
            canonical_scholarship_id TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (run_id, original_scholarship_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scholarship_dedup_match_before (
            run_id TEXT NOT NULL,
            group_number INTEGER NOT NULL,
            original_match_id TEXT NOT NULL,
            student_id TEXT NOT NULL,
            original_scholarship_id TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (run_id, original_match_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scholarship_dedup_source_identity (
            run_id TEXT NOT NULL,
            group_number INTEGER NOT NULL,
            canonical_scholarship_id TEXT NOT NULL,
            original_scholarship_id TEXT NOT NULL,
            dataset_id TEXT,
            source_filename TEXT,
            source_identifier TEXT,
            PRIMARY KEY (run_id, original_scholarship_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scholarship_dedup_child_before (
            run_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            original_row_id TEXT NOT NULL,
            original_scholarship_id TEXT NOT NULL,
            row_json TEXT NOT NULL,
            PRIMARY KEY (run_id, table_name, original_row_id)
        )
        """,
    ]
    for statement in statements:
        db.execute(statement)


def business_tables(db: sqlite3.Connection) -> list[str]:
    return sorted(
        row["name"]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        if row["name"] not in AUDIT_TABLES
    )


def table_counts(db: sqlite3.Connection) -> dict[str, int]:
    return {
        table: db.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
        for table in business_tables(db)
    }


def table_hashes(db: sqlite3.Connection) -> dict[str, str]:
    hashes = {}
    for table in business_tables(db):
        quoted = quote_identifier(table)
        primary_key = [
            row["name"]
            for row in sorted(
                db.execute(f"PRAGMA table_info({quoted})").fetchall(),
                key=lambda column: column["pk"],
            )
            if row["pk"]
        ]
        order_by = ", ".join(quote_identifier(column) for column in primary_key)
        rows = db.execute(f"SELECT * FROM {quoted} ORDER BY {order_by}").fetchall()
        digest = hashlib.sha256()
        for row in rows:
            digest.update(json_text(dict(row)).encode("utf-8"))
            digest.update(b"\n")
        hashes[table] = digest.hexdigest()
    return hashes


def candidate_groups(report: dict) -> tuple[list[dict], list[dict]]:
    excluded = []
    candidates = []
    observed_excluded_ids = set()
    for group in report["group_details"]:
        ids = set(group["all_ids"])
        if ids & EXCLUDED_GROUP_148_IDS:
            if not EXCLUDED_GROUP_148_IDS.issubset(ids):
                raise ValueError("Group 148 exclusion IDs no longer identify the expected single group")
            excluded.append(group)
            observed_excluded_ids |= ids & EXCLUDED_GROUP_148_IDS
        else:
            candidates.append(group)
    if observed_excluded_ids != EXCLUDED_GROUP_148_IDS or len(excluded) != 1:
        raise ValueError("Could not verify Group 148; refusing cleanup")
    return candidates, excluded


def child_reference_tables(db: sqlite3.Connection) -> list[str]:
    tables = []
    for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        table = row["name"]
        if table in AUDIT_TABLES or table in {"scholarships", "scholarship_matches"}:
            continue
        columns = [
            column["name"]
            for column in db.execute(f"PRAGMA table_info({quote_identifier(table)})")
        ]
        if "scholarship_id" not in columns:
            continue
        foreign_keys = db.execute(f"PRAGMA foreign_key_list({quote_identifier(table)})").fetchall()
        if any(fk["table"] == "scholarships" and fk["from"] == "scholarship_id" for fk in foreign_keys):
            tables.append(table)
    return sorted(tables)


def check_child_unique_conflicts(db: sqlite3.Connection, group: dict, tables: list[str]) -> list[dict]:
    ids = set(group["all_ids"])
    conflicts = []
    for table in tables:
        quoted = quote_identifier(table)
        rows = db.execute(
            f"SELECT * FROM {quoted} WHERE scholarship_id IN ({','.join('?' for _ in ids)})",
            sorted(ids),
        ).fetchall()
        for index in db.execute(f"PRAGMA index_list({quoted})"):
            if not index["unique"]:
                continue
            index_columns = [
                column["name"]
                for column in db.execute(f"PRAGMA index_info({quote_identifier(index['name'])})")
                if column["name"] is not None
            ]
            if "scholarship_id" not in index_columns:
                continue
            logical_key = [column for column in index_columns if column != "scholarship_id"]
            key_to_ids: dict[tuple, set[str]] = defaultdict(set)
            for row in rows:
                key = tuple(row[column] for column in logical_key)
                if any(value is None for value in key):
                    continue
                key_to_ids[key].add(row["scholarship_id"])
            for key, source_ids in key_to_ids.items():
                if len(source_ids) > 1:
                    conflicts.append({
                        "table": table,
                        "unique_index": index["name"],
                        "key_columns": logical_key,
                        "key_values": list(key),
                        "scholarship_ids": sorted(source_ids),
                    })
    return conflicts


def dry_run(path: Path) -> dict:
    db = open_read_only(path)
    try:
        report = build_report(db, path)
        candidates, excluded = candidate_groups(report)
        db_counts = {
            table: db.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}").fetchone()[0]
            for table in ["scholarships", "scholarship_matches", *CHILD_TABLES]
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        }
        return {
            "mode": "dry-run; database opened read-only",
            "database": str(path.resolve()),
            "live_database_refused_for_mutation": str(path.resolve()) == str(LIVE_DATABASE),
            "candidate_groups": len(candidates),
            "excluded_group_148": {
                "scholarship_ids": excluded[0]["all_ids"],
                "row_count": len(excluded[0]["all_ids"]),
                "match_rows": len(excluded[0]["affected_match_rows"]),
            },
            "scholarship_rows_before": db_counts.get("scholarships"),
            "eligible_duplicate_scholarship_rows": sum(len(g["all_ids"]) - 1 for g in candidates),
            "match_rows_before": db_counts.get("scholarship_matches"),
            "eligible_group_match_rows": sum(len(g["affected_match_rows"]) for g in candidates),
            "expected_group_match_rows_after": sum(g["unique_student_group_pairs"] for g in candidates),
            "child_counts_before": {k: v for k, v in db_counts.items() if k in CHILD_TABLES},
            "groups_with_match_payload_differences": [g["group"] for g in candidates if not g["match_payload_consistent"]],
            "groups_with_child_references": [
                {
                    "group": g["group"],
                    "scholarship_name": g["scholarship_rows"][g["canonical_id"]]["scholarship_name"],
                    "rows_by_table": {
                        table: detail["count"]
                        for table, detail in g["related_record_references"].items()
                        if table in CHILD_TABLES and detail["count"]
                    },
                }
                for g in candidates
                if any(
                    detail["count"]
                    for table, detail in g["related_record_references"].items()
                    if table in CHILD_TABLES
                )
            ],
            "action": "No database changes were made.",
        }
    finally:
        db.close()


def insert_json_before(db, table: str, columns: list[str], values: list) -> None:
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    db.execute(
        f"INSERT INTO {quote_identifier(table)} ({quoted_columns}) VALUES ({placeholders})",
        values,
    )


def archive_rows(db: sqlite3.Connection, run_id: str, candidates: list[dict], child_tables: list[str]) -> None:
    for group in candidates:
        group_number = group["group"]
        canonical_id = group["canonical_id"]
        for scholarship_id, row in group["scholarship_rows"].items():
            db.execute(
                "INSERT INTO scholarship_dedup_scholarship_before VALUES (?, ?, ?, ?, ?)",
                (run_id, group_number, scholarship_id, canonical_id, json_text(row)),
            )
            db.execute(
                "INSERT INTO scholarship_dedup_source_identity VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    group_number,
                    canonical_id,
                    scholarship_id,
                    row.get("dataset_id"),
                    row.get("source_filename"),
                    row.get("source_identifier"),
                ),
            )
        for row in group["affected_match_rows"]:
            db.execute(
                "INSERT INTO scholarship_dedup_match_before VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    group_number,
                    row["id"],
                    row["student_id"],
                    row["scholarship_id"],
                    json_text(row),
                ),
            )
        for table in child_tables:
            detail = group["related_record_references"].get(table, {})
            for row in detail.get("rows", []):
                if row["scholarship_id"] == canonical_id:
                    continue
                db.execute(
                    "INSERT INTO scholarship_dedup_child_before VALUES (?, ?, ?, ?, ?)",
                    (run_id, table, row["id"], row["scholarship_id"], json_text(row)),
                )


def update_canonical_provenance(db: sqlite3.Connection, group: dict) -> None:
    file_tokens = set()
    identifier_tokens = set()
    for row in group["scholarship_rows"].values():
        file_tokens.update(token.strip() for token in (row.get("source_filename") or "").split(";") if token.strip())
        identifier_tokens.update(token.strip() for token in (row.get("source_identifier") or "").split(";") if token.strip())
    if not identifier_tokens:
        raise ValueError(f"Group {group['group']} has no source identifiers; refusing automatic cleanup")
    db.execute(
        "UPDATE scholarships SET source_filename=?, source_identifier=? WHERE id=?",
        ("; ".join(sorted(file_tokens)) or None, "; ".join(sorted(identifier_tokens)), group["canonical_id"]),
    )
    actual = db.execute(
        "SELECT source_filename, source_identifier FROM scholarships WHERE id=?",
        (group["canonical_id"],),
    ).fetchone()
    if {token.strip() for token in (actual["source_filename"] or "").split(";") if token.strip()} != file_tokens:
        raise ValueError(f"Group {group['group']} source_filename provenance validation failed")
    if {token.strip() for token in (actual["source_identifier"] or "").split(";") if token.strip()} != identifier_tokens:
        raise ValueError(f"Group {group['group']} source_identifier provenance validation failed")


def reconcile_matches(db: sqlite3.Connection, group: dict) -> int:
    if group["duplicate_student_scholarship_pairs"]:
        raise ValueError(f"Group {group['group']} has duplicate student/scholarship pairs")
    if not group["match_payload_consistent"]:
        raise ValueError(f"Group {group['group']} has differing match payloads")
    by_student: dict[str, list[dict]] = defaultdict(list)
    for row in group["affected_match_rows"]:
        by_student[row["student_id"]].append(row)
    changed_count = 0
    for rows in by_student.values():
        if len(rows) == 1:
            if rows[0]["scholarship_id"] != group["canonical_id"]:
                db.execute(
                    "UPDATE scholarship_matches SET scholarship_id=? WHERE id=?",
                    (group["canonical_id"], rows[0]["id"]),
                )
                changed_count += 1
            continue
        canonical_matches = [row for row in rows if row["scholarship_id"] == group["canonical_id"]]
        if canonical_matches:
            retained = canonical_matches[0]
        else:
            retained = max(
                rows,
                key=lambda row: (row.get("updated_at") or "", row.get("calculated_at") or "", row["id"]),
            )
            db.execute(
                "UPDATE scholarship_matches SET scholarship_id=? WHERE id=?",
                (group["canonical_id"], retained["id"]),
            )
            changed_count += 1
        for row in rows:
            if row["id"] == retained["id"]:
                continue
            db.execute("DELETE FROM scholarship_matches WHERE id=?", (row["id"],))
            changed_count += 1
    return changed_count


def verify_no_duplicate_pairs(db: sqlite3.Connection) -> None:
    duplicate = db.execute(
        "SELECT student_id, scholarship_id, COUNT(*) AS n FROM scholarship_matches "
        "GROUP BY student_id, scholarship_id HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone()
    if duplicate:
        raise ValueError(f"Duplicate match pair remains: {dict(duplicate)}")


def verify_no_duplicate_references(db: sqlite3.Connection, duplicate_ids: list[str], tables: list[str]) -> None:
    for table in tables:
        placeholders = ",".join("?" for _ in duplicate_ids)
        row = db.execute(
            f"SELECT COUNT(*) FROM {quote_identifier(table)} WHERE scholarship_id IN ({placeholders})",
            duplicate_ids,
        ).fetchone()
        if row[0]:
            raise ValueError(f"{row[0]} references to duplicate scholarship IDs remain in {table}")


def validate_after_cleanup(
    db: sqlite3.Connection,
    candidates: list[dict],
    excluded: list[dict],
    before_counts: dict[str, int],
    before_hashes: dict[str, str],
    child_tables: list[str],
) -> dict:
    duplicate_ids = [
        scholarship_id
        for group in candidates
        for scholarship_id in group["all_ids"]
        if scholarship_id != group["canonical_id"]
    ]
    verify_no_duplicate_references(db, duplicate_ids, child_tables)
    verify_no_duplicate_pairs(db)
    foreign_key_errors = [dict(row) for row in db.execute("PRAGMA foreign_key_check")]
    if foreign_key_errors:
        raise ValueError(f"Foreign-key check failed: {foreign_key_errors[:5]}")
    integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise ValueError(f"SQLite integrity check failed: {integrity}")
    after_report = build_report(db, Path("test-copy"))
    remaining_groups = [group["all_ids"] for group in after_report["group_details"]]
    expected_excluded = set(excluded[0]["all_ids"])
    if remaining_groups != [sorted(expected_excluded)] and not (
        len(remaining_groups) == 1 and set(remaining_groups[0]) == expected_excluded
    ):
        raise ValueError(f"Unexpected exact-data duplicate groups remain: {remaining_groups}")
    for group in candidates:
        canonical = db.execute(
            "SELECT source_filename, source_identifier FROM scholarships WHERE id=?",
            (group["canonical_id"],),
        ).fetchone()
        files = set()
        identifiers = set()
        for row in group["scholarship_rows"].values():
            files.update(token.strip() for token in (row.get("source_filename") or "").split(";") if token.strip())
            identifiers.update(token.strip() for token in (row.get("source_identifier") or "").split(";") if token.strip())
        if {token.strip() for token in (canonical["source_filename"] or "").split(";") if token.strip()} != files:
            raise ValueError(f"Source filenames not preserved for group {group['group']}")
        if {token.strip() for token in (canonical["source_identifier"] or "").split(";") if token.strip()} != identifiers:
            raise ValueError(f"Source identifiers not preserved for group {group['group']}")
    after_counts = table_counts(db)
    expected_scholarships = before_counts["scholarships"] - sum(
        len(group["all_ids"]) - 1 for group in candidates
    )
    if after_counts["scholarships"] != expected_scholarships:
        raise ValueError("Scholarship row count does not match the approved candidate mapping")
    for table in child_tables:
        if after_counts[table] != before_counts[table]:
            raise ValueError(f"Child table count changed unexpectedly: {table}")
    return {
        "integrity_check": integrity,
        "foreign_key_errors": foreign_key_errors,
        "no_duplicate_student_scholarship_pairs": True,
        "no_references_to_removed_scholarship_ids": True,
        "remaining_exact_data_groups": remaining_groups,
        "source_identifiers_preserved": True,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "before_hashes": before_hashes,
        "after_hashes": table_hashes(db),
    }


def apply_to_test_copy(path: Path) -> dict:
    path = require_test_copy(path)
    db = open_writable(path)
    run_id = str(uuid.uuid4())
    try:
        db.execute("BEGIN IMMEDIATE")
        report = build_report(db, path)
        candidates, excluded = candidate_groups(report)
        if any(not group["match_payload_consistent"] for group in candidates):
            raise ValueError("At least one candidate group has differing match payloads")
        child_tables = child_reference_tables(db)
        conflicts = [
            conflict
            for group in candidates
            for conflict in check_child_unique_conflicts(db, group, child_tables)
        ]
        if conflicts:
            raise ValueError(f"Child unique-key conflicts found: {conflicts}")
        before_counts = table_counts(db)
        before_hashes = table_hashes(db)
        create_audit_schema(db)
        db.execute(
            "INSERT INTO scholarship_dedup_audit_runs "
            "(run_id,status,created_at,group_count,excluded_group_ids_json,before_counts_json,before_hashes_json) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                "applying",
                now_text(),
                len(candidates),
                json_text(sorted(EXCLUDED_GROUP_148_IDS)),
                json_text(before_counts),
                json_text(before_hashes),
            ),
        )
        archive_rows(db, run_id, candidates, child_tables)

        changed_child_rows = 0
        for group in candidates:
            update_canonical_provenance(db, group)
            for table in child_tables:
                for row in group["related_record_references"].get(table, {}).get("rows", []):
                    if row["scholarship_id"] == group["canonical_id"]:
                        continue
                    db.execute(
                        f"UPDATE {quote_identifier(table)} SET scholarship_id=? WHERE id=?",
                        (group["canonical_id"], row["id"]),
                    )
                    changed_child_rows += 1
            reconcile_matches(db, group)

        duplicate_ids = [
            scholarship_id
            for group in candidates
            for scholarship_id in group["all_ids"]
            if scholarship_id != group["canonical_id"]
        ]
        verify_no_duplicate_references(db, duplicate_ids, child_tables)
        for scholarship_id in duplicate_ids:
            db.execute("DELETE FROM scholarships WHERE id=?", (scholarship_id,))

        validations = validate_after_cleanup(
            db, candidates, excluded, before_counts, before_hashes, child_tables
        )
        validations["changed_child_rows"] = changed_child_rows
        validations["archived_scholarship_rows"] = sum(len(g["all_ids"]) for g in candidates)
        validations["archived_match_rows"] = sum(len(g["affected_match_rows"]) for g in candidates)
        after_counts = validations["after_counts"]
        db.execute(
            "UPDATE scholarship_dedup_audit_runs SET status='committed', finished_at=?, "
            "after_counts_json=?, validation_json=? WHERE run_id=?",
            (now_text(), json_text(after_counts), json_text(validations), run_id),
        )
        db.commit()
        return {
            "mode": "applied to test copy only",
            "database": str(path),
            "run_id": run_id,
            "excluded_group_148": sorted(EXCLUDED_GROUP_148_IDS),
            "before_counts": before_counts,
            "after_counts": after_counts,
            "validation": validations,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def restore_row(db: sqlite3.Connection, table: str, row: dict) -> None:
    quoted = quote_identifier(table)
    columns = list(row)
    primary_key = [
        info["name"]
        for info in db.execute(f"PRAGMA table_info({quoted})")
        if info["pk"]
    ]
    if not primary_key:
        raise ValueError(f"Cannot restore {table}: no primary key found")
    updates = [column for column in columns if column not in primary_key]
    sql = (
        f"INSERT INTO {quoted} ({', '.join(quote_identifier(c) for c in columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT ({', '.join(quote_identifier(c) for c in primary_key)}) DO UPDATE SET "
        + ", ".join(f"{quote_identifier(column)}=excluded.{quote_identifier(column)}" for column in updates)
    )
    db.execute(sql, [row[column] for column in columns])


def rollback_test_copy(path: Path, run_id: str) -> dict:
    path = require_test_copy(path)
    db = open_writable(path)
    try:
        run = db.execute(
            "SELECT * FROM scholarship_dedup_audit_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if run is None or run["status"] != "committed":
            raise ValueError("No committed cleanup audit run found for rollback")
        db.execute("BEGIN IMMEDIATE")
        scholarship_rows = db.execute(
            "SELECT row_json FROM scholarship_dedup_scholarship_before WHERE run_id=?",
            (run_id,),
        ).fetchall()
        for archived in scholarship_rows:
            restore_row(db, "scholarships", json.loads(archived["row_json"]))
        child_rows = db.execute(
            "SELECT table_name,row_json FROM scholarship_dedup_child_before WHERE run_id=?",
            (run_id,),
        ).fetchall()
        for archived in child_rows:
            restore_row(db, archived["table_name"], json.loads(archived["row_json"]))
        match_rows = db.execute(
            "SELECT row_json FROM scholarship_dedup_match_before WHERE run_id=?", (run_id,)
        ).fetchall()
        for archived in match_rows:
            restore_row(db, "scholarship_matches", json.loads(archived["row_json"]))
        expected_hashes = json.loads(run["before_hashes_json"])
        actual_hashes = table_hashes(db)
        if actual_hashes != expected_hashes:
            different = sorted(
                table for table in set(expected_hashes) | set(actual_hashes)
                if expected_hashes.get(table) != actual_hashes.get(table)
            )
            raise ValueError(f"Rollback table hashes do not match the pre-cleanup copy: {different}")
        integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
        foreign_key_errors = [dict(row) for row in db.execute("PRAGMA foreign_key_check")]
        if integrity != ["ok"] or foreign_key_errors:
            raise ValueError("Rollback integrity or foreign-key validation failed")
        db.execute(
            "UPDATE scholarship_dedup_audit_runs SET status='rolled_back', finished_at=? WHERE run_id=?",
            (now_text(), run_id),
        )
        db.commit()
        return {
            "mode": "rollback applied to test copy only",
            "database": str(path),
            "run_id": run_id,
            "restored_scholarship_rows": len(scholarship_rows),
            "restored_match_rows": len(match_rows),
            "restored_changed_child_rows": len(child_rows),
            "business_table_hashes_match_before_cleanup": True,
            "integrity_check": integrity,
            "foreign_key_errors": foreign_key_errors,
            "schema_note": "Audit tables remain on this test copy by design.",
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=LIVE_DATABASE)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--apply-test-copy",
        action="store_true",
        help="Apply only to an existing copy under Backend/reports/test-copies/.",
    )
    actions.add_argument("--rollback-run-id", help="Restore a committed run from its audit on a test copy.")
    args = parser.parse_args()
    try:
        if args.apply_test_copy:
            result = apply_to_test_copy(args.database)
        elif args.rollback_run_id:
            result = rollback_test_copy(args.database, args.rollback_run_id)
        else:
            result = dry_run(args.database)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as error:
        print(f"Refused or failed safely: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
