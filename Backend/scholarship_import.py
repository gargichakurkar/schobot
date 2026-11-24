"""Deprecated legacy importer entry point.

The supported scholarship import is ``python -m app.seed.import_scholarships``;
it reads only ``data/scholarships_dataset_dual_links.csv``.
"""


def import_scholarships():
    raise RuntimeError(
        "The legacy scholarship importer is disabled. Use "
        "'python -m app.seed.import_scholarships' to import the dual-links dataset."
    )


if __name__ == "__main__":
    import_scholarships()
