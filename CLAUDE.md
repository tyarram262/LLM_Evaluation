# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An "Eval-as-a-Service" API: customers POST an LLM prompt+response pair, and the platform uses a cheap/fast **judge model** (Google Gemini Flash) to grade the response on metrics (toxicity, hallucination, brand_safety) and return structured 1–10 scores. Evaluations are persisted to SQLite and retrievable; a single-page dashboard is served at `/`.

## Commands

All commands run from the project root with the venv active (`source .venv/bin/activate`).

```bash
# Install deps (first time)
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# Run the server (dashboard at http://localhost:8000, Swagger at /docs)
uvicorn main:app --reload --port 8000

# Run all tests
pytest tests/ -v --asyncio-mode=auto

# Run a single test
pytest tests/test_evaluate.py::test_successful_evaluation -v --asyncio-mode=auto

# DB migrations (production schema management; dev auto-creates tables on startup)
alembic upgrade head
alembic revision --autogenerate -m "describe change"   # after editing models in repository.py
```

There is no linter or build step configured.

## Configuration

Settings load from `.env` via `config.py` (`pydantic-settings`). Key vars: `GEMINI_API_KEY` (required), `MODEL_ID`, `MAX_TOKENS`, `REQUEST_TIMEOUT`, `MAX_RETRIES`, `DATABASE_URL` (default async SQLite: `sqlite+aiosqlite:///./evaluations.db`), `API_KEYS` (comma-separated bearer tokens, default `dev-local-key`), `RATE_LIMIT` (default `60/minute`). Copy `.env.example` to `.env` to start.

**`.env` changes require a full server restart** — `uvicorn --reload` only watches `.py` files, not `.env`. Settings are read once at import time when `Settings()` is instantiated.

**`DATABASE_URL` must use an async driver** — `sqlite+aiosqlite://` locally or `postgresql+asyncpg://` in production. A plain `sqlite://` URL will fail (the engine is async).

## Architecture

Request flow for `POST /api/v1/evaluate`:
`api/v1/routes.py` → `services/evaluator.py` (calls Gemini) → `services/repository.py` (persists) → returns scored `EvalResponse`.

Layers and their boundaries:
- **`models/schemas.py`** — Pydantic API models. `EvalRequest`/`EvalResponse` are the API contract; `EvaluationLog` is the persisted/retrieved record shape (wraps request + response).
- **`services/evaluator.py`** — owns the "judge" meta-prompt and the hardened Gemini call: per-attempt `asyncio.wait_for` timeout + tenacity exponential-backoff retry on transient codes (429/5xx). Uses Gemini **structured output** (`response_schema=_JudgeOutput`, a list-shaped model) instead of prompt-only JSON. The judge returns a `scores` *list* of `{metric, score, reasoning}`, re-keyed into a dict in `_parse_response`.
- **`services/repository.py`** — async SQLAlchemy 2.0 store behind a storage-agnostic interface (`save`/`find_by_id`/`find_by_app`, all `async`). `EvaluationModel` is the ORM table; `Base.metadata` is what Alembic autogenerates against. Engine uses `NullPool` for SQLite (avoids cross-event-loop connection reuse). **To move to PostgreSQL, only `DATABASE_URL` changes** — routes and services are untouched.
- **`auth.py`** — `require_api_key` bearer dependency, applied to the whole `/api/v1` router in `main.py`. `/health` and `/` stay public.
- **`rate_limit.py`** — slowapi `Limiter` keyed by API key (falls back to client IP). Applied via `@limiter.limit(settings.rate_limit)` on `/evaluate`; in-memory (swap to Redis `storage_uri` for multi-worker prod).
- **`main.py`** — lifespan calls `repository.create_all()` (dev convenience; prod uses Alembic). Wires the auth'd router, the rate-limiter + 429 handler, `GET /health`, and `GET /` (serves `static/index.html` via a CWD-independent `STATIC_DIR` path).
- **`static/index.html`** — dependency-free dashboard. Has an API-key field; sends `Authorization: Bearer` on every fetch. Served same-origin (no CORS).

Conventions that span files:
- **Score semantics are inverted from intuition: 1 = worst/riskiest, 10 = best/safest.** A toxic response scores *low*. The UI's color tiers and any aggregation depend on this.
- **Two distinct "models":** the customer's LLM produces the `llm_response` being graded; `MODEL_ID` is the separate *judge* model doing the grading. Don't conflate them.
- **`/evaluate` errors return HTTP 200 with `status: "error"`** in the body (not 5xx). `evaluator.evaluate()` catches Gemini failures (after retries) and malformed/invalid output (`json.JSONDecodeError`/Pydantic `ValidationError`) and returns a well-typed `EvalResponse`. Auth (401/403), rate limit (429), and request validation (422) DO use real status codes.
- **The `/evaluate` route needs `request: Request` as its first param** (required by the slowapi limiter); the JSON body is the second param `payload: EvalRequest`.
- **Module-level singletons** instantiated at import: `evaluator_service`, `repository`, the SQLAlchemy `engine`/`SessionLocal`, and `limiter`.
- **Absolute imports from project root** (e.g. `from services.evaluator import ...`) — the server and Alembic must be launched from the project root.

## Testing

`tests/conftest.py` sets `DATABASE_URL` (async SQLite temp file), `API_KEYS=test-key`, and a high `RATE_LIMIT` **before** the app imports, so tests are isolated and deterministic. The `client` fixture calls `repository.create_all()` (ASGITransport doesn't run the lifespan) and sends `Authorization: Bearer test-key` by default; `noauth_client` omits it for auth tests. Tests patch `services.evaluator.evaluator_service._client.aio.models.generate_content` with an `AsyncMock` — the mock's `.text` must be JSON matching `_JudgeOutput` (a `scores` **list**, not dict).
