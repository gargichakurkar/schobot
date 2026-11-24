"""Print exact-data scholarship duplicate groups and linked matches; never writes."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "schobot.db"
IDENTITY_AND_PROVENANCE = {
    "id",
    "dataset_id",
    "source_filename",
    "source_identifier",
    "created_at",
    "updated_at",
}


def read_only_connection(path: Path) -> sqlite3.Connection:
    absolute_path = path.resolve()
    uri = f"file:{quote(absolute_path.as_posix(), safe='/:')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _scholarship_reference_tables(connection: sqlite3.Connection) -> list[tuple[str, list[str]]]:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    result = []
    for table_row in tables:
        table_name = table_row["name"]
        quoted_name = _quote_identifier(table_name)
        columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({quoted_name})")]
        if table_name == "scholarships" or "scholarship_id" not in columns:
            continue
        foreign_keys = connection.execute(f"PRAGMA foreign_key_list({quoted_name})").fetchall()
        if any(
            row["table"] == "scholarships" and row["from"] == "scholarship_id"
            for row in foreign_keys
        ):
            result.append((table_name, columns))
    return sorted(result)


def _reference_details(
    connection: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    scholarship_ids: list[str],
) -> dict:
    quoted_name = _quote_identifier(table_name)
    placeholders = ",".join("?" for _ in scholarship_ids)
    rows = connection.execute(
        f"SELECT * FROM {quoted_name} WHERE scholarship_id IN ({placeholders}) "
        "ORDER BY scholarship_id",
        scholarship_ids,
    ).fetchall()
    counts = Counter(row["scholarship_id"] for row in rows)

    unique_key_conflicts = []
    for index in connection.execute(f"PRAGMA index_list({quoted_name})"):
        if not index["unique"]:
            continue
        index_name = _quote_identifier(index["name"])
        index_columns = [
            entry["name"]
            for entry in connection.execute(f"PRAGMA index_info({index_name})")
            if entry["name"] is not None
        ]
        if "scholarship_id" not in index_columns:
            continue
        logical_key = [column for column in index_columns if column != "scholarship_id"]
        if not logical_key:
            continue
        by_key: dict[tuple, set[str]] = defaultdict(set)
        for row in rows:
            key = tuple(row[column] for column in logical_key)
            if any(value is None for value in key):
                continue
            by_key[key].add(row["scholarship_id"])
        for key, ids in by_key.items():
            if len(ids) > 1:
                unique_key_conflicts.append(
                    {
                        "unique_index": index["name"],
                        "key_columns": logical_key,
                        "key_values": list(key),
                        "scholarship_ids": sorted(ids),
                    }
                )

    return {
        "count": len(rows),
        "counts_by_scholarship_id": {
            scholarship_id: counts[scholarship_id] for scholarship_id in scholarship_ids
        },
        "unique_key_conflicts_on_reassignment": unique_key_conflicts,
        "rows": [dict(row) for row in rows],
    }


def build_report(connection: sqlite3.Connection, database_path: Path) -> dict:
    scholarships = connection.execute("SELECT * FROM scholarships").fetchall()
    columns = [column[1] for column in connection.execute("PRAGMA table_info(scholarships)")]
    comparison_fields = [
        field for field in columns if field not in IDENTITY_AND_PROVENANCE
    ]

    groups_by_data: dict[tuple, list[sqlite3.Row]] = defaultdict(list)
    for scholarship in scholarships:
        key = tuple(scholarship[field] for field in comparison_fields)
        groups_by_data[key].append(scholarship)

    groups = [rows for rows in groups_by_data.values() if len(rows) > 1]
    groups.sort(key=lambda rows: tuple(str(rows[0][field] or "") for field in comparison_fields))

    report_groups = []
    group_summaries = []
    reference_tables = _scholarship_reference_tables(connection)
    for index, rows in enumerate(groups, start=1):
        ordered = sorted(rows, key=lambda row: (str(row["created_at"] or ""), str(row["id"])))
        canonical = ordered[0]
        duplicate_ids = [row["id"] for row in ordered[1:]]
        all_ids = [row["id"] for row in ordered]
        placeholders = ",".join("?" for _ in all_ids)
        matches = connection.execute(
            f"SELECT * FROM scholarship_matches WHERE scholarship_id IN ({placeholders}) "
            "ORDER BY student_id, scholarship_id, id",
            all_ids,
        ).fetchall()
        student_match_ids: dict[str, set[str]] = defaultdict(set)
        pair_counts = Counter()
        match_counts_by_scholarship_id = Counter()
        for match in matches:
            student_match_ids[match["student_id"]].add(match["scholarship_id"])
            pair_counts[(match["student_id"], match["scholarship_id"])] += 1
            match_counts_by_scholarship_id[match["scholarship_id"]] += 1
        collisions = {
            student_id: sorted(match_ids)
            for student_id, match_ids in student_match_ids.items()
            if len(match_ids) > 1
        }
        duplicate_pairs = [
            {"student_id": student_id, "scholarship_id": scholarship_id, "row_count": count}
            for (student_id, scholarship_id), count in sorted(pair_counts.items())
            if count > 1
        ]
        scholarship_rows = {
            row["id"]: dict(row)
            for row in ordered
        }
        payload_fields = (
            "match_status", "match_score", "passed_rules", "failed_rules",
            "unknown_rules", "warnings",
        )
        payloads_by_student: dict[str, set[tuple]] = defaultdict(set)
        for match in matches:
            payloads_by_student[match["student_id"]].add(
                tuple(match[field] for field in payload_fields)
            )
        divergent_students = sorted(
            student_id
            for student_id, payloads in payloads_by_student.items()
            if len(payloads) > 1
        )
        unique_student_group_count = len(payloads_by_student)
        related_references = {
            table_name: _reference_details(connection, table_name, table_columns, all_ids)
            for table_name, table_columns in reference_tables
        }
        linked_record_count = sum(detail["count"] for detail in related_references.values())
        reassignment_conflicts = {
            table_name: detail["unique_key_conflicts_on_reassignment"]
            for table_name, detail in related_references.items()
            if detail["unique_key_conflicts_on_reassignment"]
        }
        source_records = [
            {
                "scholarship_id": row["id"],
                "dataset_id": row["dataset_id"],
                "source_filename": row["source_filename"],
                "source_identifier": row["source_identifier"],
            }
            for row in ordered
        ]
        group_summaries.append(
            {
                "group": index,
                "scholarship_name": canonical["scholarship_name"],
                "canonical_id": canonical["id"],
                "scholarship_ids": all_ids,
                "source_records": source_records,
                "exact_business_data_match": True,
                "comparison_field_count": len(comparison_fields),
                "match_rows": len(matches),
                "unique_student_group_pairs": unique_student_group_count,
                "match_payload_consistent": not divergent_students,
                "divergent_match_payload_students": divergent_students,
                "related_record_counts": {
                    table_name: detail["counts_by_scholarship_id"]
                    for table_name, detail in related_references.items()
                },
                "linked_record_count": linked_record_count,
                "related_unique_key_reassignment_conflicts": reassignment_conflicts,
            }
        )
        report_groups.append(
            {
                "group": index,
                "canonical_id": canonical["id"],
                "duplicate_ids": duplicate_ids,
                "all_ids": all_ids,
                "scholarship_rows": scholarship_rows,
                "match_row_counts_by_scholarship_id": {
                    scholarship_id: match_counts_by_scholarship_id[scholarship_id]
                    for scholarship_id in all_ids
                },
                "duplicate_student_scholarship_pairs": duplicate_pairs,
                "unique_student_group_pairs": unique_student_group_count,
                "match_payload_consistent": not divergent_students,
                "divergent_match_payload_students": divergent_students,
                "affected_match_rows": [dict(match) for match in matches],
                "student_id_collisions": collisions,
                "related_record_references": related_references,
            }
        )

    return {
        "mode": "read-only dry run",
        "database": str(database_path.resolve()),
        "exact_data_comparison_fields": comparison_fields,
        "scholarship_rows": len(scholarships),
        "total_match_rows": connection.execute(
            "SELECT COUNT(*) FROM scholarship_matches"
        ).fetchone()[0],
        "duplicate_groups": len(report_groups),
        "extra_scholarship_rows": sum(len(group["duplicate_ids"]) for group in report_groups),
        "affected_match_rows": sum(len(group["affected_match_rows"]) for group in report_groups),
        "collision_groups": sum(bool(group["student_id_collisions"]) for group in report_groups),
        "affected_collision_students": len({
            student_id
            for group in report_groups
            for student_id in group["student_id_collisions"]
        }),
        "collision_group_student_occurrences": sum(
            len(group["student_id_collisions"]) for group in report_groups
        ),
        "collision_group_match_rows": sum(
            len(group["affected_match_rows"])
            for group in report_groups
            if group["student_id_collisions"]
        ),
        "duplicate_student_scholarship_pair_groups": sum(
            bool(group["duplicate_student_scholarship_pairs"]) for group in report_groups
        ),
        "match_payload_inconsistent_groups": sum(
            not group["match_payload_consistent"] for group in report_groups
        ),
        "groups_with_related_records": sum(
            summary["linked_record_count"] > 0 for summary in group_summaries
        ),
        "groups_with_match_rows": sum(summary["match_rows"] > 0 for summary in group_summaries),
        "groups_with_non_match_child_records": sum(
            any(
                count > 0
                for table_name, counts in summary["related_record_counts"].items()
                if table_name != "scholarship_matches"
                for count in counts.values()
            )
            for summary in group_summaries
        ),
        "related_record_rows_by_table": {
            table_name: sum(
                group["related_record_references"][table_name]["count"]
                for group in report_groups
            )
            for table_name, _ in reference_tables
        },
        "groups_with_unique_key_reassignment_conflicts": sum(
            bool(summary["related_unique_key_reassignment_conflicts"])
            for summary in group_summaries
        ),
        "expected_match_rows_after_one_per_student_group": sum(
            group["unique_student_group_pairs"] for group in report_groups
        ),
        "expected_total_match_rows_after_group_reconciliation": (
            connection.execute("SELECT COUNT(*) FROM scholarship_matches").fetchone()[0]
            - sum(len(group["affected_match_rows"]) for group in report_groups)
            + sum(group["unique_student_group_pairs"] for group in report_groups)
        ),
        "groups": group_summaries,
        "group_details": report_groups,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE,
        help=f"SQLite database to inspect (default: {DEFAULT_DATABASE})",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Omit full scholarship and match rows while retaining all 158 group summaries.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this file (filesystem only; database remains read-only).",
    )
    args = parser.parse_args()
    connection = read_only_connection(args.database)
    try:
        report = build_report(connection, args.database)
    finally:
        connection.close()
    output_report = report
    if args.summary_only:
        output_report = {key: value for key, value in report.items() if key != "group_details"}
    serialized = json.dumps(output_report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
        print(f"Read-only report written to {args.output.resolve()}")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
