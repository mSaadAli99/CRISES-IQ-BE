# CrisisIQ Backend — Setup & ADK

## Python version

Works on **Python 3.11–3.14**. Uses **psycopg3** for async Postgres (no `asyncpg` compile step).

Recommended: 3.12. See `.python-version`.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

For local Google ADK tracing (`CRISISIQ_ADK_MODE=llm` or `adk web`), install the optional ADK dependencies:

```powershell
pip install -r requirements-adk.txt
```

## Environment

```powershell
copy .env.example .env
# Edit .env: NEON_DATABASE_URL, GEMINI_API_KEY
```

To use Vertex AI instead of Gemini API-key free-tier quotas, enable the Vertex AI API for your GCP project and use a least-privilege service account with the `Vertex AI User` role. For Vercel, store the service-account JSON in an environment variable, not in Git.

## Verify before push

```powershell
python scripts\verify_setup.py
```

## Run server

```powershell
uvicorn main:app --reload --port 8000
```

## Deploy on Railway

1. **Root Directory:** `backend` (repo root only has `backend/` + `.gitignore`).
2. **Start command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. **Variables:** `NEON_DATABASE_URL`, `GEMINI_API_KEY` (and optional `GEMINI_MODEL`, `CRISISIQ_ADK_MODE`).
4. **Networking:** Generate a public domain so the frontend can reach the API.

The app uses **psycopg3** (`postgresql+psycopg://`) for async Postgres — `asyncpg` is not required and must not be used unless you add it to `requirements.txt`.

## Deploy on Vercel

1. **Framework preset:** FastAPI
2. **Root Directory:** `./`
3. **Variables:** `NEON_DATABASE_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-2.5-flash`, `CRISISIQ_ADK_MODE=direct`.

Vercel has a 500 MB Lambda bundle limit, so `requirements.txt` excludes the optional `google-adk` package. The deployed `/api/adk/pipeline` endpoint uses the direct tool-chain mode by default.

### Vercel with Vertex AI

Use these variables to route LLM calls through Vertex AI:

```text
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=whatsappbot-493906
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS_JSON={...service account json...}
GEMINI_MODEL=gemini-2.5-flash
```

You can use `GOOGLE_APPLICATION_CREDENTIALS_JSON_BASE64` instead of `GOOGLE_APPLICATION_CREDENTIALS_JSON` if your deployment UI handles single-line values better.

## ADK endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/pipeline` | Original Python pipeline |
| `POST /api/adk/pipeline` | Google ADK tools pipeline (demo) |

`CRISISIQ_ADK_MODE=direct` (default) or `llm` in `.env`.

## Quick test

```powershell
curl -X POST http://localhost:8000/api/seed
curl -X POST http://localhost:8000/api/adk/pipeline -H "Content-Type: application/json" -d "{\"location\":\"Lyari Karachi\",\"signal_ids\":[]}"
```
