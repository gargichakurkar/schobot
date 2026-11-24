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
- Do not introduce LLM-based eligibility decisions.
- Do not add heavy new dependencies unless strictly necessary.
- Keep the code modular, typed, and consistent with the existing style.
- Preserve the folder structure and naming conventions already in use.
- Ensure all code works with the current SQLite development setup.
