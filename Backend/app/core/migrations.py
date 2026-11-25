from __future__ import annotations

from sqlalchemy import Engine, Text, inspect


SCHOLARSHIP_COLUMNS = {
    "milestones": "JSON",
    "provider": "VARCHAR(255)",
    "additional_category_requirements": "TEXT",
    "additional_income_requirements": "TEXT",
    "benefits": "TEXT",
    "required_documents": "TEXT",
    "eligibility_details": "TEXT",
    "scheme_info_link": "VARCHAR(500)",
    "minimum_marks_text": "TEXT",
    "additional_education_requirements": "TEXT",
    "gender_requirement": "VARCHAR(255)",
    "year_text": "VARCHAR(100)",
    "source_filename": "TEXT",
    "source_identifier": "TEXT",
    "active_status": "VARCHAR(30)",
}


def migrate_scholarship_columns(engine: Engine) -> None:
    columns = inspect(engine).get_columns("scholarships")
    existing_columns = {column["name"] for column in columns}
    missing_columns = {
        name: column_type
        for name, column_type in SCHOLARSHIP_COLUMNS.items()
        if name not in existing_columns
    }
    category_column = next(
        (column for column in columns if column["name"] == "category"),
        None,
    )
    if engine.dialect.name == "postgresql" and category_column is None:
        raise RuntimeError(
            "The scholarships.category column is missing and cannot be migrated to TEXT."
        )
    category_type = category_column["type"] if category_column is not None else None
    migrate_category_type = (
        engine.dialect.name == "postgresql"
        and category_type is not None
        and not isinstance(category_type, Text)
    )
    if not missing_columns and not migrate_category_type:
        return

    with engine.begin() as connection:
        for name, column_type in missing_columns.items():
            connection.exec_driver_sql(
                f"ALTER TABLE scholarships ADD COLUMN {name} {column_type}"
            )
        if migrate_category_type:
            connection.exec_driver_sql(
                "ALTER TABLE scholarships "
                "ALTER COLUMN category TYPE TEXT USING category::text"
            )


def migrate_document_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Migrate documents table if it exists
    if "documents" in tables:
        columns = inspector.get_columns("documents")
        existing_columns = {column["name"] for column in columns}
        ts_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
        doc_columns = {
            "original_filename": "VARCHAR(255)",
            "file_name": "VARCHAR(255)",
            "storage_path": "VARCHAR(500)",
            "mime_type": "VARCHAR(100)",
            "file_size": "INTEGER",
            "ocr_status": "VARCHAR(50)",
            "extracted_fields": "JSON",
            "verification_status": "VARCHAR(50)",
            "expiry_date": ts_type,
            "rejection_reason": "TEXT",
            "verified_by": "VARCHAR(100)",
            "verified_at": ts_type,
            "created_at": ts_type,
            "updated_at": ts_type,
        }
        missing_doc = {name: ctype for name, ctype in doc_columns.items() if name not in existing_columns}
        if missing_doc:
            with engine.begin() as connection:
                for name, ctype in missing_doc.items():
                    connection.exec_driver_sql(f"ALTER TABLE documents ADD COLUMN {name} {ctype}")

    # Migrate student_scholarship_documents if it exists
    if "student_scholarship_documents" in tables:
        columns = inspector.get_columns("student_scholarship_documents")
        existing_columns = {column["name"] for column in columns}
        if "matched_document_id" not in existing_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE student_scholarship_documents ADD COLUMN matched_document_id VARCHAR(36)"
                )

