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
