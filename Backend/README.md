# Backend diagnostics

## Import the scholarship catalogue

From `Backend`, import only the dual-links source into the configured
`scholarships` table with:

```powershell
.\venv\Scripts\python.exe -m app.seed.import_scholarships
```

The importer defaults to `..\data\scholarships_dataset_dual_links.csv`; an
optional `--dual-csv` argument can point to another file. `scholar.csv` remains
in `data` but is no longer imported. The old `/import-scholarships` route and
`scholarship_import.py` database writer are disabled.

The dual-links file maps `offered_by`, current education, eligible categories,
family income, benefits, documents, marks, gender criteria, and both links to
their separate columns. It has no state, scholarship type, or current
application status column, so those values are left unknown rather than
inferred. Repeat imports match rows by a deterministic fingerprint of name,
provider, category, and official portal.

## Destructive reset and reseed (review before use)

Do not use this for an ordinary import. It deletes scholarship rows and their
student match, progress, scholarship document, and scholarship reminder rows,
then imports only the dual-links CSV. Student profiles and unrelated records remain. Scholarship
UUIDs are generated on insertion, so reset changes them; old dependent records
are explicitly cleared rather than left pointing at missing scholarships.
Users must regenerate matches and re-enter progress/document/reminder settings after
the reset. The command creates a timestamped SQLite backup beside the
configured database before its first database change. Without the exact
confirmation phrase it prints the affected row counts and exits without
changing the database or creating a backup.

From `Backend`, first review affected row counts without confirmation:

```powershell
.\venv\Scripts\python.exe -m app.seed.reset_and_reseed_scholarships
```

Only after reviewing the warning and counts, run:

```powershell
.\venv\Scripts\python.exe -m app.seed.reset_and_reseed_scholarships --confirm RESET-SCHOLARSHIPS
```

## Start the API

From `Backend`:

```powershell
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Start the frontend from `Frontend` with:

```powershell
npm run dev
```

The Available Scholarships page loads the database catalogue. Eligibility
recommendations remain profile-based; records with unknown current status can
be evaluated but are not labeled currently active, and unsupported criteria
remain `needs_verification`.

## Scholarship deadlines and documents

Recommendation responses include each scholarship's existing `deadline` and
`official_link` values. Missing deadlines are shown as TBD; confirm deadlines
on the provider's official website. Document status and notes are saved per
student, scholarship, and document. The dual-links file's `key_documents_required`
field is retained as the source checklist.
