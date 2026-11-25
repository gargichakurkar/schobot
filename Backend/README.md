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

## Incremental official scholarship fetching

The fetcher currently has one operational adapter: the National Scholarship
Portal (NSP). AICTE and MahaDBT remain disabled until their adapters are
implemented and tested. The fetcher keeps the existing 13-column dataset
mapping; it does not change the CSV files.

Run one discovery-only cycle from `Backend`:

```powershell
python -m app.services.scholarship_fetcher.nsp_fetcher --discovery-only --source nsp
```

Discovery-only mode does not insert or update rows in `scholarships`, but it
does write ingestion run, state, and event records. It also creates the four
ingestion trace tables if they do not exist. Therefore, it is not a no-write
operation and should only be run against a local/test database unless that
trace-table creation has been approved for the target database.

To persist validated new and changed NSP records, run:

```powershell
python -m app.services.scholarship_fetcher.nsp_fetcher --persist --source nsp
```

Do not use `--schedule` for Render Cron Jobs; each cron invocation is already a
single run. Configure the Render Cron Job with:

- **Root directory:** `Backend`
- **Build command:** `pip install -r requirements.txt`
- **Command:** `python -m app.services.scholarship_fetcher.nsp_fetcher --persist --source nsp`
- **Schedule:** `0 2 * * *` (Render cron time is UTC; this is 7:30 AM IST)

Set `DATABASE_URL` to the approved PostgreSQL connection string. `GROQ_API_KEY`
is optional: without it, deterministic extraction continues and fields that
cannot be verified remain unknown. If Groq extraction is enabled, the fetcher
uses the configured `GROQ_MODEL`. Never put credentials in the command or
repository.

The fetcher records run status, counts, application periods, per-record
previous/current hashes, and errors in the ingestion trace tables. Review the
latest Render job logs and run record before treating a cycle as successful:

```sql
SELECT started_at, completed_at, status, statistics, error
FROM scholarship_ingestion_runs
WHERE source_key = 'nsp'
ORDER BY started_at DESC
LIMIT 10;
```

NSP requests use a descriptive `ScholarMateScholarshipFetcher` user agent and
check the source's `robots.txt` policy before fetching. A missing robots file
(HTTP 404) is treated as no published robots rules; access-denied, rate-limited,
and server-error responses fail closed. The code applies a one-second interval
between guideline requests and retries transient failures with backoff,
honoring short `Retry-After` values on rate limits. It defers a retry when the
requested wait exceeds its configured limit. This does not replace checking
NSP's current terms of use; no live fetch has been performed as part of local
validation.

The repository has no separate migration file for the ingestion trace tables;
the fetch command creates those tables through SQLAlchemy `create_all()` if
they are absent. Confirm the production database owner approves this
non-destructive schema creation and that the job's database role has the
required `CREATE TABLE` permission before enabling the Render job. The fetcher
does not delete scholarships merely because they are absent from a listing.

## Scholarship deadlines and documents

Recommendation responses include each scholarship's existing `deadline` and
`official_link` values. Missing deadlines are shown as TBD; confirm deadlines
on the provider's official website. Document status and notes are saved per
student, scholarship, and document. The dual-links file's `key_documents_required`
field is retained as the source checklist.
