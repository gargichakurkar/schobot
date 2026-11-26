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


def migrate_student_auth_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    ts_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"

    # Migrate student_profiles for password authentication and email OTP
    if "student_profiles" in tables:
        columns = inspector.get_columns("student_profiles")
        existing = {c["name"] for c in columns}
        auth_columns = {
            "password_hash": "VARCHAR(255)",
            "otp_hash": "VARCHAR(255)",
            "otp_expires_at": ts_type,
            "otp_attempts": "INTEGER DEFAULT 0",
        }
        missing = {name: ctype for name, ctype in auth_columns.items() if name not in existing}
        if missing:
            with engine.begin() as connection:
                for name, ctype in missing.items():
                    connection.exec_driver_sql(f"ALTER TABLE student_profiles ADD COLUMN {name} {ctype}")

        # Check for email uniqueness safety before adding unique index
        with engine.begin() as connection:
            dup_query = (
                "SELECT LOWER(email) AS em, COUNT(*) AS cnt "
                "FROM student_profiles "
                "WHERE email IS NOT NULL AND email != '' "
                "GROUP BY LOWER(email) "
                "HAVING COUNT(*) > 1"
            )
            try:
                duplicates = connection.exec_driver_sql(dup_query).fetchall()
                if duplicates:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Found %d duplicate email group(s) in student_profiles. "
                        "Skipping unique index creation to protect existing records without data loss: %s",
                        len(duplicates),
                        [d[0] for d in duplicates[:5]],
                    )
                else:
                    if engine.dialect.name == "postgresql":
                        connection.exec_driver_sql(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_student_profiles_lower_email "
                            "ON student_profiles (LOWER(email)) "
                            "WHERE email IS NOT NULL AND email != ''"
                        )
                    else:
                        connection.exec_driver_sql(
                            "CREATE UNIQUE INDEX IF NOT EXISTS uq_student_profiles_lower_email "
                            "ON student_profiles (email COLLATE NOCASE)"
                        )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Could not check or create unique index on student_profiles.email: %s", exc
                )

    # Migrate counselor_links for expiry and revocation lifecycle
    if "counselor_links" in tables:
        columns = inspector.get_columns("counselor_links")
        existing = {c["name"] for c in columns}
        bool_type = "BOOLEAN DEFAULT FALSE"
        counselor_cols = {
            "expires_at": ts_type,
            "is_revoked": bool_type,
        }
        missing = {name: ctype for name, ctype in counselor_cols.items() if name not in existing}
        with engine.begin() as connection:
            if missing:
                for name, ctype in missing.items():
                    connection.exec_driver_sql(f"ALTER TABLE counselor_links ADD COLUMN {name} {ctype}")
            # Safely backfill existing links with expires_at = created_at + 30 days
            if engine.dialect.name == "postgresql":
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET expires_at = created_at + INTERVAL '30 days' "
                    "WHERE expires_at IS NULL AND created_at IS NOT NULL"
                )
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET expires_at = NOW() + INTERVAL '30 days' "
                    "WHERE expires_at IS NULL"
                )
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET is_revoked = FALSE WHERE is_revoked IS NULL"
                )
            else:
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET expires_at = datetime(created_at, '+30 days') "
                    "WHERE expires_at IS NULL AND created_at IS NOT NULL"
                )
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET expires_at = datetime('now', '+30 days') "
                    "WHERE expires_at IS NULL"
                )
                connection.exec_driver_sql(
                    "UPDATE counselor_links SET is_revoked = 0 WHERE is_revoked IS NULL"
                )
