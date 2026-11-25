# Schobot Certificate Scanning and RAG Status

## Status

The scanner now retrieves real passages from a restricted, local corpus of official Maharashtra sources using locally computed sentence-transformer embeddings. It does not use Supabase, pgvector, an external LLM, or student-uploaded documents as knowledge-base material.

The feature is **not ready for public deployment**:

- Tesseract is not installed, so real image/scanned-PDF OCR and English/Marathi OCR have not been verified.
- The active application has no authenticated user/login flow. The scan endpoint is rate-limited but still has no authentication; do not expose it publicly until an authentication design is approved and implemented.
- Caste Validity and Nationality official guidance remain incomplete; retrieval is not a legal determination.

## Files changed for this continuation

- `Backend/app/services/certificate_knowledge.py` — replaced keyword-only source summaries with a locally parsed, hashed, category-allowlisted corpus; page-aware chunking; local embeddings; cosine retrieval; and source excerpts with provenance.
- `Backend/app/services/document_service.py` — builds the retrieval query from the selected certificate type and temporary OCR text; returns the retrieved official excerpts and preserves the explicit “not evaluated” requirements status.
- `Backend/app/routers/documents.py` — added an in-process per-client rate limit of 20 scans per minute and explicit 503 handling when the local knowledge base is unavailable. Upload closure and the existing file-size limit remain in place.
- `Backend/tests/test_document_scanning.py` — tests category isolation, exact directory-row ingestion, runtime source fingerprints, actual PDF text-layer extraction, and rate limiting.
- `Frontend/src/pages/CertificateScanner.jsx` and `Frontend/src/pages/CertificateScanner.css` — display retrieved official passages and PDF page citations.
- `docs/document_ai/document_scanning_rag_scope_report.md` — updated status and limitations.

The eight files in `Backend/app/data/certificate_sources/originals/` were already downloaded from official government hosts and were not modified in this continuation. No requirements, models, migrations, database records, scholarship logic, or `.env` files were changed.

## Approved source audit

The corpus is defined by a fixed source allowlist. At runtime, each local file is SHA-256 fingerprinted; retrieval references include the fingerprint, source URL, title, issuer, type, version/language metadata, retrieval timestamp, similarity score, and the retrieved text. The broad services-directory page is reduced to one exact service row. Service-detail HTML is reduced to its service form. No other rows or page navigation are indexed.

| Local source file | Official source / issuing authority | Coverage and ingestion |
|---|---|---|
| `income_certificate_application.pdf` | [Application for Income Certificate (1 year / 3 year)](https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Income_Certificate.pdf) — Maharashtra Revenue Department | English/Marathi form; PDF text is chunked with page numbers. The 2014 form is not treated as a universal checklist. |
| `aaple_income_service.html` | [Income Certificate service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1251) — Aaple Sarkar / Revenue Department | Only the matching service form is extracted; English page with Marathi alternate link. |
| `aaple_caste_service.html` | [Caste Certificate service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1284) — Aaple Sarkar / Revenue Department | Only the matching service form is extracted; broad evidence examples are not represented as universal legal requirements. |
| `maharashtra_caste_act_modified_2012.pdf` | [Maharashtra Act No. XXIII of 2001 — Caste Certificate Act, 2000](https://cdnbbsr.s3waas.gov.in/s36a4cbdaedcbda0fa8ddc7ea32073c475/uploads/2025/02/20250210421165874.pdf) — Law and Judiciary Department | Extractable official English text is indexed for Caste and Caste Validity. The copy states it is modified through 29 October 2012; it is not verified as current through 2026. |
| `maharashtra_caste_certificate_rules_2012.pdf` | [Caste Certificate Rules, 2012](https://cdnbbsr.s3waas.gov.in/s3b090409688550f3cc93f4ed88ec6cafb/uploads/2025/01/202501131491187877.pdf) — Social Justice and Special Assistance Department | Scanned Gazette with no extractable text; explicitly excluded from retrieval. It must not be summarized from OCR that has not been run or verified. |
| `aaple_certificate_services.html` | [Department Notified Services directory](https://aaplesarkar.mahaonline.gov.in/en/CommonForm/ViewAllServices) — Aaple Sarkar | Only the row for “Caste Certificate Verification Committee” is indexed for Caste Validity; all unrelated service rows are excluded. This row is a directory listing, not complete validity guidance. |
| `age_nationality_domicile_application.pdf` | [Application for Age, Nationality and Domicile Certificate](https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Age_Nationality_and%20Domicile_Certificate.pdf) — Maharashtra Revenue Department | English/Marathi combined form; PDF text is chunked with page numbers. It does not prove a universal domicile residence period. |
| `aaple_age_nationality_domicile_service.html` | [Age, Nationality and Domicile service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1253) — Aaple Sarkar / Revenue Department | Only the matching service form is extracted for Domicile and Nationality. This is a combined service, not a standalone nationality-only process. |

No scholarship PDFs, arbitrary websites, general certificate sources, or non-allowlisted certificate types are ingested. Nationality retrieval remains limited to the combined Maharashtra Age, Nationality and Domicile sources; no independent nationality-only requirements are inferred.

## Retrieval implementation

- Local source text is split into approximately 1,100-character chunks with 160-character overlap. PDF page numbers are retained.
- `sentence-transformers/all-MiniLM-L6-v2` computes normalized embeddings locally; cosine similarity ranks passages after certificate-type allowlisting.
- The model and vectors are held in process memory. They are not written to a database or index file. `local_files_only=True` prevents model downloads; a deployment must provision the model cache or the scanner returns HTTP 503.
- Uploaded certificate bytes and extracted text are never added to the source corpus, persisted, logged, or sent to an external embedding/LLM service. OCR text is used only as a transient local retrieval query.
- Retrieved official excerpts are evidence for source discovery only. They do not prove authenticity, define all requirements, or determine eligibility.

## OCR, upload handling, and security

- Existing validation accepts only PDF/JPG/JPEG/PNG with extension, MIME and file-signature checks; request processing is capped at 10 MB. Existing OCR limits include 25 megapixels, 15 PDF pages, 100,000 extracted characters, bounded per-call OCR, and a 90-second total PDF OCR ceiling.
- The upload is read with a bounded read and `UploadFile.close()` runs in a `finally` block. No permanent certificate storage or student-document indexing was added.
- An in-process rate limit allows at most 20 scan requests per client address in a rolling 60-second window. This is not a distributed limiter and may need trusted-proxy-aware identity handling in a multi-worker deployment.
- **Authentication is still missing.** `auth.py` contains JWT/password helpers, but the active application has no selected/operational login flow. Profile IDs are not authentication. A trusted identity provider or approved first-party login design is required before public exposure.
- The local OCR package `pytesseract` is present, but the Tesseract executable is absent from `PATH`; `pytesseract.get_tesseract_version()` reports that Tesseract is not installed. Real OCR of images or scanned PDFs therefore did not run. Existing OCR-path tests that mock Tesseract are not evidence of actual OCR. English and Marathi trained-data availability is unverified.
- A real local PDF text-layer extraction test passes. This tests PDF parsing, not OCR.
- No request was made to Supabase during the later, explicitly SQLite-forced test runs. No claim is made that the earlier PostgreSQL-configured test imports had no schema side effects (see validation note below).

## Test and build results

- Focused scanner tests: run against in-memory SQLite; see final local test output. They cover all five category values, unsupported categories/files, extracted/missing fields, duplicate values, category allowlisting, source hashes and exclusions, exact Caste Validity directory-row scope, PDF text extraction, OCR-path mocks, unavailable OCR reporting, and rate limiting.
- Full backend suite against in-memory SQLite: **138 passed, 3 failed**.
  1. `test_default_dataset_is_autosaved_file_with_47_rows` — current CSV contains 46 rows, not 47. The dataset was not changed.
  2. `test_import_is_dual_source_only_and_idempotent` — test expects the old report key `scholarships_dataset_dual_links.csv`; the importer reports the configured Autosaved filename.
  3. `test_reset_transaction_rolls_back_import_and_validation_failures[validation]` — test double returns the old filename key, while reset code reads the Autosaved key.
- The recommendation test `test_profile_update_automatically_refreshes_recommendations` failed once in a combined focused invocation, then passed when run alone and in the full suite. It was not reproducible and no rule-engine changes were made.
- Frontend production build: **passed**.
- Frontend lint: **completed with one existing warning** in `src/components/ReminderPreferences.jsx:17`; no scanner warning was reported.

## Database validation safety note

Two earlier backend test invocations in this continuation ran before the configured database backend was checked. They imported `app.main`, which executes `Base.metadata.create_all(bind=engine)` and `migrate_scholarship_columns(engine)` at module import. The configured backend was PostgreSQL, so those invocations **may have connected and applied schema-only DDL** (creating missing tables/columns or altering `scholarships.category`). The tests did not invoke the scholarship importer or issue record-level application writes. I did not reconnect to inspect the database, and cannot confirm whether any DDL was applied or whether that PostgreSQL endpoint is production. After discovering this, all later backend checks explicitly set `DATABASE_URL=sqlite://`; no later PostgreSQL connection was attempted.

## Remaining work before public deployment

1. Select and implement a trusted authentication flow; do not rely on profile IDs or a frontend-embedded API secret.
2. Obtain approval before retrying Tesseract installation or selecting another OCR engine. Then verify `eng` and `mar` language data with real synthetic PDF and image fixtures.
3. OCR and manually review the scanned Caste Rules PDF and verify later amendments before indexing it.
4. Continue research for current caste-validity guidance, community schedules, standalone nationality guidance, and verified domicile residence rules.
5. Provide an operator-led review of PostgreSQL audit/schema state independently; no further database access is performed by this report.
