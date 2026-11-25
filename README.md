# Schobot

## Project overview

Schobot is a transparent scholarship recommendation system for students who need a clear, explainable match against available scholarships. The MVP prioritizes deterministic eligibility logic over black-box recommendation behavior: rules decide whether a student is eligible, AI explains the result in plain language, and the official scholarship portal remains the final authority for approval.

The architecture is intentionally simple and auditable. It avoids LLM-based eligibility decisions and instead combines a rule engine, structured matching records, and a clean API for student profiles, scholarship recommendations, and eligibility explanations.

## Tech stack

- Python 3.12+
- FastAPI
- SQLAlchemy
- Pydantic
- Pandas
- pytest
- SQLite for development
- PostgreSQL as the target production database

## Project structure

- app/main.py — FastAPI application entrypoint
- app/core/ — configuration and database wiring
- app/models/ — SQLAlchemy models
- app/schemas/ — request/response validation models
- app/repositories/ — persistence helpers
- app/services/ — business logic, scoring, and eligibility rules
- app/routers/ — API endpoints
- app/seed/ — data import utilities
- app/utils/ — helper functions and normalizers
- tests/ — rule engine and API validation tests

## Setup instructions

### 1) Create and activate a virtual environment

```bash
cd Backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Configure environment variables

Create a `.env` file inside the Backend directory:

```env
DATABASE_URL=sqlite:///./schobot.db
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
SECRET_KEY=development-secret-key
```

### 4) Run the API

```bash
cd Backend
uvicorn app.main:app --reload
```

On Windows, run this from the `Backend` directory:

```powershell
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Use `app.main:app` for the current API. `Backend/main.py` now forwards to that
same app for compatibility, while the former standalone legacy API is available
as `legacy_main:app`. If an old server is already running, stop it with
`Ctrl+C` before restarting it with the command above.

Verify the server and profile-save endpoint from another PowerShell window:

```powershell
Invoke-RestMethod -Uri 'http://localhost:8000/api/health' -TimeoutSec 5

$body = @{
  full_name = "Test User"
  email = "test@example.com"
  education_level = "Undergraduate"
  course = "B.Tech"
  study_year = "2nd Year"
  college_name = "Test College"
  academic_score = 85
  score_type = "Percentage"
  domicile_state = "Maharashtra"
  study_state = "Maharashtra"
  category = "OBC"
  gender = "Female"
  annual_family_income = 600000
  profile_completed = $true
} | ConvertTo-Json -Depth 10

$response = Invoke-RestMethod `
  -Method Post `
  -Uri 'http://localhost:8000/api/profile/submit-and-recommend' `
  -ContentType 'application/json' `
  -Body $body
Write-Output "Student ID: $($response.student.id)"
Write-Output "Recommendations count: $($response.recommendations.Count)"
```

### 5) Run tests

```bash
cd Backend
pytest -q
```

## CSV import instructions

The active scholarship source is `data/scholarships_dataset_dual_links.csv`.
`data/scholar.csv` is retained but is not imported.

Run the import script:

```bash
cd Backend
python -m app.seed.import_scholarships
```

What the script does:

- reads the source CSV from the project data folder
- normalizes column names
- removes empty rows and duplicate IDs
- maps raw CSV columns into the scholarship model fields
- attempts to extract `max_income`, `min_percentage`, `eligible_level`, `eligible_course`, `is_active`, and `deadline` when the source text is clear enough
- inserts or updates scholarship rows in the current SQLite-backed database
- prints a short import summary for review

The API startup creates missing database tables without deleting existing rows.
The importer reads only the dual-links CSV. To remove the current catalogue and
its match/progress/document rows before reseeding, review the warning and counts
using the no-confirmation reset command documented in `Backend/README.md`; the
reset requires the explicit `RESET-SCHOLARSHIPS` confirmation phrase and makes
a timestamped SQLite backup first. It has not been run as part of this change.
For local debugging, set `SCHOBOT_DEBUG_ELIGIBILITY=1` before starting the API to
log one rule evaluation; the log includes student income and category, so use a
synthetic profile and unset the variable afterward.

## API usage examples

### Create a student profile

```bash
curl -X POST http://localhost:8000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Asha Verma",
    "email": "asha@example.com",
    "education_level": "Undergraduate",
    "course": "B.Tech",
    "study_year": "2",
    "college_name": "ABC College",
    "academic_score": 92,
    "score_type": "percentage",
    "domicile_state": "Maharashtra",
    "study_state": "Maharashtra",
    "category": "General",
    "gender": "Female",
    "has_disability_certificate": false,
    "annual_family_income": 180000,
    "has_income_certificate": true,
    "profile_completed": true
  }'
```

### Submit profile and get recommendations

```bash
curl -X POST http://localhost:8000/api/profile/submit-and-recommend \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Mehul Patil",
    "email": "mehul@example.com",
    "education_level": "Undergraduate",
    "course": "B.Tech",
    "study_year": "2",
    "college_name": "State Tech Institute",
    "academic_score": 87,
    "score_type": "percentage",
    "domicile_state": "Maharashtra",
    "study_state": "Maharashtra",
    "category": "General",
    "gender": "Male",
    "has_disability_certificate": false,
    "annual_family_income": 180000,
    "has_income_certificate": true,
    "profile_completed": true
  }'
```

### Get recommendations for a student

```bash
curl http://localhost:8000/api/recommendations/{student_id}
```

### Get a single scholarship

```bash
curl http://localhost:8000/api/scholarships/{scholarship_id}
```

### Get eligibility explanation for one scholarship and one student

```bash
curl http://localhost:8000/api/scholarships/{scholarship_id}/eligibility/{student_id}
```

## Rule engine explanation

The eligibility engine checks these items in order:

1. scholarship is active
2. deadline is valid
3. state or domicile matches the requirement
4. category matches
5. education level matches
6. eligible course matches
7. minimum academic score is met
8. family income is within the cap
9. gender requirement matches
10. disability requirement is considered where relevant

### Match statuses

- `likely_eligible`: all required checks pass
- `needs_verification`: some important data is missing or unclear
- `not_matched`: a required hard rule fails
- `expired`: the scholarship deadline has passed

### Scoring formula

The engine starts at 100, then:

- subtracts 25 for each failed hard rule
- subtracts 10 for each unknown or missing important rule
- adds 5 for an exact state/domicile match
- adds 5 for an exact course match
- adds 5 when an official scholarship link is present and looks valid
- clamps the final score between 0 and 100

## Dataset information

The current MVP source is `data/scholarships_dataset_dual_links.csv`. The
other CSV files remain available in the repository but are not active import
sources.

This phase intentionally does not integrate the much larger historical outcomes dataset; the MVP focuses on the structured scholarship catalog and rule-based matching workflow.

## Constraints and guardrails

- Keep rule-engine normalization narrow, transparent, and covered by tests; preserve the existing match statuses.
- Do not introduce LLM-based eligibility decisions. The deterministic Python rule engine is the single source of truth.
- Do not add heavy new dependencies to the web service. Heavy ML/worker dependencies are isolated to `requirements-worker.txt`.
- Keep the code modular, typed, and consistent with the existing style.
- Preserve the folder structure and naming conventions already in use.
- Ensure all code works with the current SQLite development setup and PostgreSQL in production.

---

## Production Deployment & Render 512 MB Optimization

### Architecture & Memory Optimization
The backend is optimized to run reliably within **Render's Free Tier (512 MiB RAM limit)**:
1. **Lazy Imports**: Heavy ML and OCR libraries (`sentence-transformers`, `torch`, `pypdfium2`) are loaded on-demand rather than at application boot, reducing startup heap from **279 MiB to ~22 MiB (92% reduction)**.
2. **Single Worker Uvicorn**: Runs with `--workers 1` to prevent multiple Python processes from exhausting memory.
3. **Dual Requirements Isolation**:
   - `Backend/requirements.txt`: Lightweight web dependencies required for the FastAPI API.
   - `Backend/requirements-worker.txt`: Additional ML, PDF, and ingestion libraries for background jobs.
4. **Controlled DB Lifecycle**: Table migrations run within the FastAPI `lifespan` handler instead of top-level import time.
5. **Database Scheme Compatibility**: Automatically normalizes Render/Supabase `postgres://` URLs to `postgresql://` and enables connection pooling (`pool_pre_ping=True`, `pool_recycle=300`).

### Deploying to Render via Blueprint (`render.yaml`)
A single `render.yaml` configuration defines both services:
1. **Web Service (`schobot-backend`)**:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`
   - Health check: `/api/health`
2. **24-Hour Cron Ingestion Job (`schobot-scholarship-sync`)**:
   - Schedule: `0 3 * * *` (Daily at 3:00 AM UTC)
   - Build: `pip install -r requirements-worker.txt`
   - Start: `python -m app.services.scholarship_fetcher.nsp_fetcher --persist --source nsp`

### Deploying the Frontend to Vercel
```bash
cd Frontend
npm install
npm run build
```
Set `VITE_API_URL` to your Render backend URL (e.g., `https://schobot-backend.onrender.com`).

---

## Demonstration Guide (Instructor / ISR Review)

### Workflow A: Profile Setup & Instant Recommendations
1. Open the web application and navigate to **My Profile**.
2. Enter student information:
   - Full Name: `Asha Verma`
   - Education: `Undergraduate`, Course: `B.Tech`, Year: `2nd Year`
   - Domicile & Study State: `Maharashtra`
   - Category: `General` (or `OBC`, `SC`, `ST`, `SEBC`, `VJNT`)
   - Gender: `Female`
   - Annual Family Income: `1,50,000`
   - Academic Score: `88%`
3. Click **Save Profile**. Recommendations recalculate atomically without duplicate rows or stale data.

### Workflow B: Explainable Eligibility ("Why You Match This Scholarship")
1. Navigate to **Eligible Scholarships** and click on a recommended scholarship (e.g. *Pragati Scholarship Scheme for Girl Students*).
2. Inspect the **"Why You Match This Scholarship"** section:
   - **Status Banner**: Displays `Likely Eligible`, `Needs Verification`, or `Not Eligible` with exact percentage match.
   - **Group A (Requirements You Meet)**: Lists each passed condition (gender, education level, course, income cap, academic score) with verified evidence.
   - **Group B (Requirements You Do Not Meet)**: Explains any disqualifying condition.
   - **Group C (Needs Verification)**: Highlights unverified documents or missing criteria.

### Workflow C: AI Chat Assistant with Conversational Grounding
1. Navigate to the **AI Assistant** tab.
2. Select language preference: **English**, **Hindi (हिंदी)**, or **Marathi (मराठी)**.
3. Ask: *"What is the deadline for Pragati Scholarship?"*
4. Ask a follow-up question: *"How can I apply for it?"* — Notice the assistant resolves *"it"* using multi-turn conversation history.
5. Inquire: *"Am I eligible?"* — Notice the assistant explains results from the deterministic rule engine rather than hallucinating eligibility.

### Workflow D: Voice Assistant (STT & TTS)
1. In the AI Assistant, click the **Microphone** icon and speak a question.
2. The transcribed question appears in the input box, allowing the student to **review and edit before sending**.
3. Click the **Speaker** icon on any response to hear natural speech output in English, Hindi, or Marathi with all Markdown syntax and URLs automatically stripped.

### Workflow E: Certificate Intelligence & Verification
1. Navigate to **Certificate Scanner**.
2. Upload a sample Income, Caste, or Domicile certificate (PDF or image).
3. The system extracts key fields locally without storing sensitive data, surfaces candidates for student confirmation, and links grounded guidelines from official government gazettes.

### Workflow F: 24-Hour Autonomous Scholarship Ingestion
1. The ingestion pipeline runs via `python -m app.services.scholarship_fetcher.nsp_fetcher --persist --source nsp`.
2. Verifies domains against the official allowlist (`scholarships.gov.in`, `mahadbt.maharashtra.gov.in`).
3. SHA256 fingerprints prevent duplicate ingestion while updating existing records idempotently.
