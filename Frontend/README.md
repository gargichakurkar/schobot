# Schobot

Student scholarship directory built with React, Vite, and React Router. The
frontend uses the FastAPI backend for saved profiles, recommendations, and
scholarship eligibility details. Available Scholarships continues to use the
repository CSV, and the AI Assistant remains simulated.

## Requirements

- Node.js 20.19+ or 22.12+
- npm

## Run the backend and frontend

Start the backend in one PowerShell terminal:
```powershell
cd Backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

Start the frontend in another PowerShell terminal:
```powershell
cd Frontend
npm install
npm run dev
```

Open the Vite URL printed in the terminal (normally `http://localhost:5173`).
The frontend API base URL is configured with `VITE_API_URL` in `Frontend/.env`
and defaults to `http://localhost:8000`.
Set `VITE_API_URL=http://localhost:8000` in `Frontend/.env` when needed and
restart Vite after changing it. If the browser reports a CORS error, ensure the
backend allows the frontend origin (`http://localhost:5173` or
`http://127.0.0.1:5173`), or use the same host consistently during development.

## Routes

- `/` — Available Scholarships and the home overview
- `/profile` — Student Profile; saved by the backend and cached locally
- `/eligible` — Backend recommendations for the saved student
- `/scholarship/:id` — Backend scholarship information and eligibility rules
- `/assistant` — Simulated assistant with predefined responses

Scholarship listings load from the repository CSV at `data/scholar.csv`.
Profile, recommendation, and detail requests use the configured FastAPI
backend. When it is unavailable, locally saved profile details remain available
and the relevant page shows a message. The assistant does not make API calls;
always verify requirements and apply through the official provider.

If Eligible Scholarships shows no results, confirm the backend is running and
save your profile again to refresh its recommendations. Available Scholarships
and the AI Assistant are local-only/simulated for now.

## Verify

```powershell
npm run lint
npm run build
```
