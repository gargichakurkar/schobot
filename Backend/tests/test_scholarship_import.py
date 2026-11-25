from __future__ import annotations

import csv
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.main import app
from app.models.scholarship import Scholarship
from app.seed.import_scholarships import (
    DATA_DIRECTORY,
    DUAL_FILENAME,
    _read_csv,
    import_scholarship_datasets,
    map_dual_row,
)
from app.seed import import_scholarships, reset_and_reseed_scholarships
from app.utils.dedupe import dedupe_by_scholarship_id


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'scholarship-tests.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def test_read_csv_supports_utf8_bom_and_windows_1252(tmp_path):
    headers = "scholarship_name,offered_by\n"
    utf8_path = tmp_path / "utf8-bom.csv"
    utf8_path.write_bytes(("\ufeff" + headers + "First Award,Provider\n").encode("utf-8"))
    windows_path = tmp_path / "windows-1252.csv"
    windows_path.write_bytes((headers + "Scholar’s Award,Provider\n").encode("cp1252"))

    required_columns = {"scholarship_name", "offered_by"}
    assert _read_csv(utf8_path, required_columns)[0]["scholarship_name"] == "First Award"
    assert _read_csv(windows_path, required_columns)[0]["scholarship_name"] == "Scholar’s Award"


def test_default_dataset_is_autosaved_file_with_47_rows():
    assert DUAL_FILENAME == "scholarships_dataset_dual_links (Autosaved).csv"
    rows = _read_csv(DATA_DIRECTORY / DUAL_FILENAME, {"scholarship_name", "offered_by"})
    assert len(rows) in {46, 47}


def test_dry_run_previews_import_and_rolls_back(db_session, tmp_path):
    dual_csv = tmp_path / DUAL_FILENAME
    write_csv(
        dual_csv,
        ["scholarship_name", "offered_by"],
        [{"scholarship_name": "Preview Award", "offered_by": "Preview Provider"}],
    )

    report = import_scholarship_datasets(db_session, dual_csv, dry_run=True)

    assert report[DUAL_FILENAME] == {
        "rows": 1,
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "invalid": 0,
    }
    assert report["final_record_count"] == 1
    assert report["preview"] == [
        {"row": 1, "scholarship_name": "Preview Award", "action": "inserted"}
    ]
    assert db_session.query(Scholarship).count() == 0


def test_dry_run_rolls_back_updates_and_reports_multiple_record_actions(db_session, tmp_path):
    columns = ["scholarship_name", "offered_by", "Type", "State"]
    initial_csv = tmp_path / "initial.csv"
    write_csv(
        initial_csv,
        columns,
        [
            {
                "scholarship_name": "Update Award",
                "offered_by": "Provider A",
                "Type": "Private",
                "State": "",
            },
            {
                "scholarship_name": "Unchanged Award",
                "offered_by": "Provider B",
                "Type": "Government",
                "State": "",
            },
        ],
    )
    import_scholarship_datasets(db_session, initial_csv)

    dry_run_csv = tmp_path / "dry-run.csv"
    write_csv(
        dry_run_csv,
        columns,
        [
            {
                "scholarship_name": "Update Award",
                "offered_by": "Provider A",
                "Type": "Public",
                "State": "",
            },
            {
                "scholarship_name": "Unchanged Award",
                "offered_by": "Provider B",
                "Type": "Government",
                "State": "",
            },
            {
                "scholarship_name": "Inserted Award",
                "offered_by": "Provider C",
                "Type": "Private",
                "State": "",
            },
            {
                "scholarship_name": "Inserted Award",
                "offered_by": "Provider C",
                "Type": "Private",
                "State": "",
            },
            {
                "scholarship_name": "",
                "offered_by": "Provider D",
                "Type": "Private",
                "State": "",
            },
        ],
    )

    report = import_scholarship_datasets(db_session, dry_run_csv, dry_run=True)

    assert report[DUAL_FILENAME] == {
        "rows": 5,
        "inserted": 1,
        "updated": 1,
        "unchanged": 1,
        "skipped": 1,
        "invalid": 1,
    }
    assert report["final_record_count"] == 3
    assert db_session.query(Scholarship).count() == 2
    updated = db_session.query(Scholarship).filter_by(scholarship_name="Update Award").one()
    assert updated.scholarship_type == "Private"
    assert (
        db_session.query(Scholarship)
        .filter_by(scholarship_name="Inserted Award")
        .count()
        == 0
    )


def test_dry_run_database_constraint_error_rolls_back(db_session, tmp_path):
    db_session.execute(
        text(
            "CREATE TRIGGER reject_long_category BEFORE INSERT ON scholarships "
            "WHEN length(NEW.category) > 10 "
            "BEGIN SELECT RAISE(ABORT, 'category too long'); END"
        )
    )
    db_session.commit()
    dual_csv = tmp_path / DUAL_FILENAME
    write_csv(
        dual_csv,
        ["scholarship_name", "offered_by", "eligible_castes_or_categories"],
        [
            {
                "scholarship_name": "Constrained Award",
                "offered_by": "Provider",
                "eligible_castes_or_categories": "Long category value",
            }
        ],
    )

    with pytest.raises(IntegrityError):
        import_scholarship_datasets(db_session, dual_csv, dry_run=True)

    assert db_session.query(Scholarship).count() == 0


def test_import_error_rolls_back_flushed_records(db_session, tmp_path, monkeypatch):
    dual_csv = tmp_path / DUAL_FILENAME
    write_csv(
        dual_csv,
        ["scholarship_name", "offered_by"],
        [
            {"scholarship_name": "First Award", "offered_by": "Provider"},
            {"scholarship_name": "Second Award", "offered_by": "Provider"},
        ],
    )
    apply_record = import_scholarships._apply_record
    calls = 0

    def fail_on_second_record(scholarship, record):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated import failure")
        return apply_record(scholarship, record)

    monkeypatch.setattr(import_scholarships, "_apply_record", fail_on_second_record)

    with pytest.raises(RuntimeError, match="simulated import failure"):
        import_scholarship_datasets(db_session, dual_csv)

    assert db_session.query(Scholarship).count() == 0


def test_source_mappers_normalize_fields_without_fabricating_values():
    dual_row = {
        "scholarship_name": " Pragati Scholarship ",
        "offered_by": "AICTE",
        "current_education": "Degree or Diploma in Engineering",
        "eligible_castes_or_categories": "Open to all categories (General, OBC, SC, ST)",
        "family_income_limit": "Less than Rs. 8.00 Lakh per annum",
        "benefits_provided": "Rs. 50,000 per year",
        "key_documents_required": "Admission letter, Income certificate",
        "official_portal_link": "https://example.gov/app",
        "scheme_info_link": "https://example.gov/scheme",
        "minimum_marks": "50% or above",
        "gender_restrictions": "Female students only",
        "Type": " Government ",
        "State": " Maharashtra ",
    }
    dual = map_dual_row(dual_row)
    without_added_fields = map_dual_row(
        {key: value for key, value in dual_row.items() if key not in {"Type", "State"}}
    )
    assert dual["provider"] == "AICTE"
    assert dual["scholarship_type"] == "Government"
    assert dual["state"] == "Maharashtra"
    assert dual["source_identifier"] == without_added_fields["source_identifier"]
    assert dual["category"] == "All Categories"
    assert dual["max_income"] == 800_000
    assert dual["benefits"] == "Rs. 50,000 per year"
    assert dual["required_documents"] == "Admission letter, Income certificate"
    assert dual["official_link"] == "https://example.gov/app"
    assert dual["scheme_info_link"] == "https://example.gov/scheme"
    assert dual["min_percentage"] == 50
    assert dual["gender_requirement"] == "Female"
    assert dual["state"] == "Maharashtra"


def test_import_is_dual_source_only_and_idempotent(db_session, tmp_path):
    dual_csv = tmp_path / "scholarships_dataset_dual_links.csv"
    dual_columns = [
        "scholarship_name", "offered_by", "current_education",
        "eligible_castes_or_categories", "family_income_limit",
        "benefits_provided", "key_documents_required", "official_portal_link",
        "scheme_info_link", "minimum_marks", "gender_restrictions",
    ]
    write_csv(
        dual_csv,
        dual_columns,
        [
            {
                "scholarship_name": "School Support Scheme",
                "offered_by": "Ministry of Education",
                "current_education": "Class 1 to Class 10",
                "eligible_castes_or_categories": "Wards of Beedi and Cine workers",
                "family_income_limit": "Monthly income of parents not exceeding Rs. 10,000",
                "benefits_provided": "Tuition support",
                "key_documents_required": "Income certificate",
                "official_portal_link": "https://scholarships.gov.in/",
                "scheme_info_link": "https://education.gov.in/school-support",
                "minimum_marks": "",
                "gender_restrictions": "",
            },
            {
                "scholarship_name": "Regional School Support",
                "offered_by": "Regional Foundation",
                "current_education": "Class 1 to Class 10",
                "eligible_castes_or_categories": "All categories",
                "family_income_limit": "",
                "benefits_provided": "",
                "key_documents_required": "",
                "official_portal_link": "https://foundation.example/apply",
                "scheme_info_link": "https://foundation.example/info",
                "minimum_marks": "",
                "gender_restrictions": "",
            },
        ],
    )

    first = import_scholarship_datasets(db_session, dual_csv)
    assert first["scholarships_dataset_dual_links.csv"] == {
        "rows": 2,
        "inserted": 2,
        "updated": 0,
        "unchanged": 0,
        "skipped": 0,
        "invalid": 0,
    }
    assert first["unique_records"] == 2

    merged = db_session.query(Scholarship).filter_by(scholarship_name="School Support Scheme").one()
    assert merged.provider == "Ministry of Education"
    assert merged.benefits == "Tuition support"
    assert merged.required_documents == "Income certificate"
    assert merged.official_link == "https://scholarships.gov.in/"
    assert merged.scheme_info_link == "https://education.gov.in/school-support"
    assert merged.active_status == "unknown"
    assert merged.is_active is False
    assert merged.category == "Wards Of Beedi And Cine Workers"
    assert merged.qualification_text == "Class 1 to Class 10"
    assert merged.income_text == "Monthly income of parents not exceeding Rs. 10,000"
    assert merged.max_income is None
    assert merged.source_filename == "scholarships_dataset_dual_links.csv"

    second = import_scholarship_datasets(db_session, dual_csv)
    assert second["scholarships_dataset_dual_links.csv"]["unchanged"] == 2
    assert second["unique_records"] == 2


def test_cross_source_match_requires_matching_education():
    row = {
        "scholarship_name": "Top Class Education Scheme",
        "offered_by": "Ministry",
        "current_education": "Engineering, Medicine, Law",
        "eligible_castes_or_categories": "SC",
        "family_income_limit": "",
        "benefits_provided": "",
        "key_documents_required": "",
        "official_portal_link": "https://scholarships.gov.in/",
        "scheme_info_link": "https://ministry.gov.in/scheme",
        "minimum_marks": "",
        "gender_restrictions": "",
    }
    dual = map_dual_row(row)
    assert dual["scholarship_name"] == "Top Class Education Scheme"
    assert "Undergraduate" not in dual["eligible_level"]


@pytest.mark.parametrize("failure_kind", ["import", "validation"])
def test_reset_transaction_rolls_back_import_and_validation_failures(
    db_session, tmp_path, monkeypatch, failure_kind
):
    db_session.add(Scholarship(id="existing-id", scholarship_name="Existing award"))
    db_session.commit()

    def failing_import(db, source):
        db.add(Scholarship(id="temporary-id", scholarship_name="Partial import"))
        db.flush()
        if failure_kind == "import":
            raise ValueError("simulated import failure")
        return {
            "scholarships_dataset_dual_links.csv": {
                "rows": 1,
                "inserted": 1,
                "updated": 0,
                "unchanged": 0,
                "skipped": 0,
                "invalid": 1,
            },
            "unique_records": 1,
        }

    monkeypatch.setattr(
        reset_and_reseed_scholarships,
        "import_scholarship_datasets",
        failing_import,
    )
    with pytest.raises((ValueError, RuntimeError)):
        reset_and_reseed_scholarships.reset_and_import_in_transaction(
            db_session, tmp_path / "dual.csv"
        )

    assert [row.id for row in db_session.query(Scholarship).all()] == ["existing-id"]


def test_duplicate_api_results_keep_first_backend_result_by_scholarship_id():
    results = dedupe_by_scholarship_id(
        [
            {"scholarship_id": "award-1", "match_status": "likely_eligible", "match_score": 90},
            {"scholarship_id": "award-1", "match_status": "ineligible", "match_score": 0},
            {"scholarship_id": "award-2", "match_status": "needs_verification", "match_score": 50},
        ]
    )

    assert results == [
        {"scholarship_id": "award-1", "match_status": "likely_eligible", "match_score": 90},
        {"scholarship_id": "award-2", "match_status": "needs_verification", "match_score": 50},
    ]


def test_list_endpoint_reads_database_and_supports_filters(db_session):
    db_session.add_all(
        [
            Scholarship(
                scholarship_name="Maharashtra Study Grant",
                provider="State Education Department",
                state="Maharashtra",
                category="SC",
                qualification_text="Undergraduate",
                eligible_level="Undergraduate",
                scholarship_type="Government",
                description="Local grant",
                is_active=False,
                active_status="unknown",
            ),
            Scholarship(
                scholarship_name="National Study Grant",
                provider="National Education Office",
                state="All India",
                category="SC",
                qualification_text="Undergraduate",
                eligible_level="Undergraduate",
                scholarship_type="Government",
                is_active=False,
                active_status="unknown",
            ),
            Scholarship(
                scholarship_name="Private Study Grant",
                provider="Private Trust",
                state="Maharashtra",
                category="OBC",
                qualification_text="Postgraduate",
                eligible_level="Postgraduate",
                scholarship_type="Private",
                is_active=False,
                active_status="unknown",
            ),
        ]
    )
    db_session.commit()

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/scholarships",
                params={
                    "state": "Maharashtra",
                    "category": "SC",
                    "education": "Undergraduate",
                    "scholarship_type": "Government",
                },
            )
            assert response.status_code == 200, response.text
            records = response.json()
            assert {item["scholarship_name"] for item in records} == {
                "Maharashtra Study Grant",
                "National Study Grant",
            }
            assert records[0]["active_status"] == "unknown"

            searched = client.get("/api/scholarships", params={"search": "Private Trust"})
            assert searched.status_code == 200
            assert [item["scholarship_name"] for item in searched.json()] == [
                "Private Study Grant"
            ]
    finally:
        app.dependency_overrides.pop(get_db, None)
