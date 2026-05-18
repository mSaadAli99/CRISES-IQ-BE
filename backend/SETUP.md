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

## Environment

```powershell
copy .env.example .env
# Edit .env: NEON_DATABASE_URL, GEMINI_API_KEY
```

## Verify before push

```powershell
python scripts\verify_setup.py
```

## Run server

```powershell
uvicorn main:app --reload --port 8000
```

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
