# LLM Observability & Evaluation API

Eval-as-a-Service: customers POST an LLM prompt+response pair, and the platform uses a cheap/fast judge model (Google Gemini Flash) to grade it on metrics (toxicity, hallucination, brand safety) and return structured 1–10 scores. Evaluations are persisted and retrievable, and a single-page dashboard is served at `/`.

> **Score scale is inverted:** 1 = worst/riskiest, 10 = best/safest. A toxic response scores *low*.

## Local development

```bash
# 1. Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env          # then set GEMINI_API_KEY

# 3. Run (dashboard at http://localhost:8000, Swagger at /docs)
uvicorn main:app --reload --port 8000
```

The dev server auto-creates SQLite tables on startup, so no migration step is needed locally.

## Tests

```bash
pytest tests/ -v --asyncio-mode=auto
# single test:
pytest tests/test_evaluate.py::test_successful_evaluation -v --asyncio-mode=auto
```

## API

All `/api/v1` routes require `Authorization: Bearer <key>` (keys configured via `API_KEYS`). `/health` and `/` are public.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/evaluate` | Grade a prompt+response; returns scores + stored `id`. Rate-limited per key. |
| GET | `/api/v1/evaluations/{id}` | Retrieve one stored evaluation |
| GET | `/api/v1/evaluations?app_id=X&limit=N` | List an app's evaluations, newest first |
| GET | `/health` | Liveness check (public) |

```bash
curl -X POST http://localhost:8000/api/v1/evaluate \
  -H "Authorization: Bearer dev-local-key" -H "Content-Type: application/json" \
  -d '{"app_id":"demo","user_prompt":"...","llm_response":"...","eval_metrics":["toxicity","hallucination","brand_safety"]}'
```

## Configuration

All settings come from environment variables / `.env` (see [.env.example](.env.example)): `GEMINI_API_KEY`, `MODEL_ID`, `MAX_TOKENS`, `REQUEST_TIMEOUT`, `MAX_RETRIES`, `DATABASE_URL`, `API_KEYS`, `RATE_LIMIT`.

## Database migrations (production)

Schema is managed by Alembic. Local dev uses `create_all()` on startup; production should run migrations:

```bash
alembic upgrade head          # apply migrations
alembic revision --autogenerate -m "describe change"   # after model changes
```

## Deployment

Containerized via the [Dockerfile](Dockerfile) (Gunicorn + Uvicorn workers). The container runs `alembic upgrade head` then starts the server, honoring `$PORT` and `$WEB_CONCURRENCY`.

```bash
docker build -t llm-eval .
docker run -p 8000:8000 --env-file .env llm-eval
```

For a real deployment (Render / Railway / Cloud Run):
1. Provision a **Postgres** instance and set `DATABASE_URL=postgresql+asyncpg://...` (SQLite does not persist on ephemeral container filesystems).
2. Set `GEMINI_API_KEY`, `API_KEYS` (real per-customer keys), and `RATE_LIMIT` as platform secrets.
3. For multiple workers/instances, point rate limiting at Redis (see `rate_limit.py`).

## Architecture

```
api/v1/routes.py   → HTTP endpoints (auth + rate limit applied here)
services/evaluator.py → judge meta-prompt, Gemini call (timeout + retry + structured output)
services/repository.py → async SQLAlchemy store (SQLite local / Postgres prod)
models/schemas.py  → Pydantic request/response/log models
static/index.html  → dependency-free dashboard
alembic/           → DB migrations
```

The repository interface is storage-agnostic — swapping SQLite for Postgres touches only `DATABASE_URL`, not application code.
