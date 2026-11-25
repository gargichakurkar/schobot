# Schobot Document Scanning and RAG Scope Report

## 1. Files inspected and modified

### Inspected

- Backend: `app/main.py`, `app/core/config.py`, `app/core/database.py`, `app/core/migrations.py`, `app/models/document.py`, `app/routers/documents.py`, `app/services/document_service.py`, `app/services/ocr_service.py`, `app/services/scholarship_fetcher/nsp_fetcher.py`, `requirements.txt`, and the backend test suite.
- Frontend: `src/App.jsx`, `src/apiClient.js`, `src/components/Sidebar.jsx`, `src/components/Icon.jsx`, scholarship document-checklist UI, and existing page/form styles.
- Existing official-source research: `docs/research/official_certificate_sources.md` and `docs/research/official_certificate_legal_gaps.md`.
- Local SQLite schemas and aggregate `documents` row counts only. No document text, filenames, student identifiers, `.env` values, Supabase data, or production services were accessed.

### Modified or added

- `Backend/app/routers/documents.py` — replaced the placeholder GET response with a bounded `POST /api/documents/scan` endpoint.
- `Backend/app/services/document_service.py` — validates upload type and signatures, detects a small set of candidate fields, returns uncertainty and source references, and does not persist documents.
- `Backend/app/services/ocr_service.py` — extracts PDF text and performs OCR for images or rendered scanned-PDF pages.
- `Backend/app/services/certificate_knowledge.py` — added the five-category allowlist and provenance-bearing official-source reference summaries.
- `Backend/requirements.txt` — added `pypdfium2` for rendering scanned PDF pages.
- `Backend/tests/test_document_scanning.py` — added upload, extraction, category-isolation, missing-field, and OCR-path tests.
- `Frontend/src/App.jsx` and `Frontend/src/components/Sidebar.jsx` — registered the scanner route and navigation entry.
- `Frontend/src/apiClient.js` — added multipart upload support without forcing a JSON content type.
- `Frontend/src/pages/CertificateScanner.jsx` and `Frontend/src/pages/CertificateScanner.css` — added the upload, status, editable review, warnings, and source-reference UI.
- `docs/document_ai/document_scanning_rag_scope_report.md` — this report.
- Vite build output generated: `Frontend/dist/index.html`, `Frontend/dist/assets/index-Bk-Iq5yn.js`, `Frontend/dist/assets/index-DEkvPmmr.css`, plus the copied `favicon.svg` and `icons.svg` assets. These are build artifacts, not source changes.

No model, migration, database record, scholarship CSV, eligibility rule, recommendation service, AI Assistant, or `.env` file was changed.

## 2. Approved RAG source references

The repository previously contained **no official source PDFs, certificate corpus, FAISS/vector index, embedding files, or RAG database tables**. The entries below are therefore a restricted, provenance-bearing reference catalogue built from the existing verified research; the application does not download or index remote pages at request time. Retrieved summaries are not verbatim replacements for the source documents.

| Category | Approved official reference | Authority and type | Verification / coverage |
|---|---|---|---|
| Income Certificate | [Application for Income Certificate (1 year / 3 year)](https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Income_Certificate.pdf) | Maharashtra Revenue Department; PDF form | Opened and inspected; PDF metadata reports 15–16 April 2014. Checklist examples are conditional, not universal requirements. |
| Income Certificate | [Income Certificate service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1251) | Maharashtra Aaple Sarkar; service page | Opened and inspected; no page version date displayed. |
| Caste Certificate | [Caste Certificate service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1284) | Maharashtra Aaple Sarkar; service page | Opened and inspected; broad evidence menu is not a universal checklist. |
| Caste Certificate | [Maharashtra Act No. XXIII of 2001 — Caste Certificate Act, 2000](https://cdnbbsr.s3waas.gov.in/s36a4cbdaedcbda0fa8ddc7ea32073c475/uploads/2025/02/20250210421165874.pdf) | Maharashtra Law and Judiciary Department; PDF Act | Opened; title and “modified through 29 October 2012” version statement inspected. Not verified as current through 2026. |
| Caste Certificate | [Caste Certificate Rules, 2012](https://cdnbbsr.s3waas.gov.in/s3b090409688550f3cc93f4ed88ec6cafb/uploads/2025/01/202501131491187877.pdf) | Maharashtra Social Justice and Special Assistance Department; Gazette PDF | Opened; pages 1–3 inspected. Later amendments and full scanned text were not verified. |
| Caste Validity Certificate | [Department Notified Services directory](https://aaplesarkar.mahaonline.gov.in/en/CommonForm/ViewAllServices) | Maharashtra Aaple Sarkar; service directory | Opened; verifies a separate Caste Certificate Verification Committee service. Complete current validity guidance remains unavailable. |
| Domicile Certificate | [Application for Age, Nationality and Domicile Certificate](https://revenue.mahaonline.gov.in/Site/Common/Documents/Downloads/Application_form_for_Age_Nationality_and%20Domicile_Certificate.pdf) | Maharashtra Revenue Department; PDF form | Opened and inspected; PDF metadata reports 15–16 April 2014. It does not establish a universal residence period. |
| Domicile / Nationality | [Age, Nationality and Domicile service detail](https://aaplesarkar.mahaonline.gov.in/en/Login/Certificate_Documents?ServiceId=1253) | Maharashtra Aaple Sarkar; service page | Opened and inspected; supports the combined service, not a separate Maharashtra nationality-only checklist. |

For **Nationality Certificate**, retrieval is deliberately limited to the combined Maharashtra Age, Nationality and Domicile service and form. The interface states that separate nationality-certificate requirements have not been established. Central citizenship procedures are not included in this Maharashtra certificate knowledge base.

The app applies certificate-type filtering before keyword ranking and returns the official title, issuer, URL, document type, available version/date, verification scope, limitations, retrieval method, score, and retrieval timestamp. It does not send certificate OCR text to a model or remote source.

**Known source gaps:** The original Form G/Form T 2012 Government Resolution was not verified; a caste Act/Rules consolidation current through 2026, current community schedules and underlying community-specific orders, complete caste-validity guidance, a universal domicile residence threshold, standalone Maharashtra nationality requirements, certificate specimens, and QR/digital-signature verification instructions are not established by the available sources. The scanner therefore does not evaluate these legal or authenticity questions.

## 3. Excluded documents and reasons

- No raw certificate-source documents or RAG index files were present in the repository scan.
- The local `documents` table exists but contained zero rows in the primary local database, named local backups, and the hidden local test database. Only aggregate counts were queried.
- No local vector tables or index files were found. No document rows were deleted.
- Scholarship guideline extraction in the NSP fetcher, scholarship `required_documents` fields, and the scholarship checklist UI are not part of the certificate knowledge base.
- General scholarship PDFs, arbitrary web pages, unsupported uploaded file types, and certificate types outside the five-item allowlist are excluded. There was no unrelated RAG corpus to remove.

## 4. Backend implementation status

- `POST /api/documents/scan` accepts one selected certificate type and PDF/JPG/JPEG/PNG uploads.
- Uploads are read with a 10 MB limit, checked against extension, declared MIME type, and file signature, then closed. Images are limited to 25 megapixels; PDFs to 15 pages; extracted text to 100,000 characters; OCR calls have per-call and 90-second total PDF OCR time limits.
- PDF text layers use `pypdf`; image and scanned-PDF pages use Tesseract, with `pypdfium2` rendering scanned PDF pages.
- Deterministic field candidates are limited to applicant name, certificate number, issue date, and issuing authority. Missing values are labelled “not detected”; detected values remain uncertain until a person reviews them. Conflicting repeated values are surfaced as possible inconsistencies.
- Available procedural references are shown, but the requirement comparison is explicitly marked `not_evaluated`: the verified sources do not define a complete standard for fields on issued certificates.
- There is no upload persistence, database migration, source-URL fetcher, vector embedding store, or generative answer step. This avoids claiming the source catalogue is a complete legal authority.

## 5. Frontend implementation status

- Added the Certificate Scanner route and navigation entry without changing existing pages.
- The page provides selection among exactly the five permitted categories, PDF/JPG/PNG upload, a busy/progress state, extracted candidate fields, missing/unreadable warnings, possible inconsistencies, and official references.
- Candidate values can be edited and marked reviewed in page state. Neither the file, extracted text, corrections, nor review status are stored in browser storage or the backend.
- The page emphasizes that OCR does not establish authenticity, QR/barcode validity, digital-signature validity, or legal validity.

## 6. OCR and RAG testing results

- New scanner tests cover all five category values, unsupported categories and files, field candidates, missing fields, duplicate values, official-source category restrictions, image OCR invocation, scanned-PDF rendering/OCR invocation, and explicit OCR-unavailable responses. OCR engines were mocked; no certificate data or external portal was used.
- Complete backend suite: **133 passed, 4 failed**. The failures are outside the changed scanner files:
  1. `test_profile_update_automatically_refreshes_recommendations` expects an `annual_income` failure rule that is absent; the same failure reproduced when run alone.
  2. `test_default_dataset_is_autosaved_file_with_47_rows` found 46 rows in the existing CSV.
  3. `test_import_is_dual_source_only_and_idempotent` expected a different importer report key.
  4. `test_reset_transaction_rolls_back_import_and_validation_failures[validation]` raised a report-key `KeyError`.
- Focused scanner, AI Assistant, and rule-engine tests: **81 passed**.
- Frontend production build: **passed**. Frontend lint completed with one warning in unchanged `src/components/ReminderPreferences.jsx:17`.
- Browser check: `/documents` rendered, all five categories appeared, and selecting Nationality displayed the combined-service limitation.
- This environment has the Python `pytesseract` package but no Tesseract executable at the checked standard Windows locations. Real OCR was therefore not run; OCR unit paths were mocked. Runtime OCR requires Tesseract plus configured `eng` and `mar` language data (`SCHOBOT_OCR_LANGUAGES`, default `eng+mar`).

## 7. Security considerations

- Uploaded data is not persisted by the application; multipart parsing may use short-lived temporary spooling, and the `UploadFile` is closed after a bounded read. The feature does not write documents or extracted text to the database, filesystem corpus, or logs. Only detected field values/evidence are returned to the requesting client.
- File type, content signature, size, image dimensions, PDF page count, extracted-text size, and OCR time are bounded. Password-protected PDFs are rejected.
- The route does not fetch caller-supplied URLs and cannot index arbitrary uploads.
- Existing Schobot APIs do not provide authentication for this route. Although this implementation has no document retrieval endpoint or persistent upload storage, add authentication and rate limiting before exposing the API to the public internet. Serve the API over HTTPS in production.
- OCR output is untrusted and must be checked against the original. The scanner must not be used as proof of authenticity or to decide scholarship eligibility.

## 8. Existing scholarship functionality

No scholarship models, CSV mapping, fetcher, migrations, recommendation rules, recommendation service, or AI Assistant code was changed. Relevant rule-engine and assistant tests passed. The full-suite failures above are recorded separately and were not “fixed” by changing unrelated behavior.

No Supabase connection, production API, migration, deployment, or database write was performed.
