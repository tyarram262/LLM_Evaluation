# Deploying to Render

This app ships with a [render.yaml](render.yaml) Blueprint that provisions the API service **and** a managed Postgres database together.

## Prerequisites

- A [Render](https://render.com) account (free).
- A **fresh** Gemini API key — rotate the one used during development; it was exposed in plaintext. Get one at https://aistudio.google.com/app/apikey.
- Strong production API keys for your customers (not `dev-local-key`). Generate one:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

## 1. Push the deploy config

The repo already has the Dockerfile and render.yaml. Commit and push them:

```bash
git add render.yaml Dockerfile DEPLOY.md config.py
git commit -m "Add Render deploy config"
git push origin master
```

## 2. Create the Blueprint on Render

1. Render dashboard → **New +** → **Blueprint**.
2. Connect your GitHub and select **`tyarram262/LLM_Evaluation`**.
3. Render reads `render.yaml` and shows the plan: a web service (`llm-eval-api`) + a Postgres database (`llm-eval-db`). Click **Apply**.

`DATABASE_URL` is wired automatically from the database; the app rewrites the scheme to `postgresql+asyncpg://` on load (see `config.py`).

## 3. Set the secret env vars

In the `llm-eval-api` service → **Environment**, fill the three `sync:false` secrets:

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | your fresh Gemini key |
| `API_KEYS` | your generated token(s), comma-separated for multiple customers |
| `SENTRY_DSN` | (optional) your Sentry DSN, or leave blank |

Save — Render redeploys automatically.

## 4. What happens on deploy

Render builds the Dockerfile, then the container start command runs:

```
alembic upgrade head   →   gunicorn (Uvicorn workers) on $PORT
```

So the Postgres schema is migrated automatically before the server starts.

## 5. Verify

Your URL will be `https://llm-eval-api.onrender.com` (or similar).

```bash
# Public health check
curl https://llm-eval-api.onrender.com/health

# Authenticated evaluation
curl -X POST https://llm-eval-api.onrender.com/api/v1/evaluate \
  -H "Authorization: Bearer <YOUR_PROD_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"prod-test","user_prompt":"hi","llm_response":"hello","eval_metrics":["toxicity"]}'
```

Then open the URL in a browser for the dashboard — enter your production API key in the field at the top right.

## Free-tier caveats

- **Cold starts:** free web services spin down after ~15 min idle; the first request then takes ~50s to wake.
- **Postgres expiry:** Render's free Postgres is deleted after 90 days. Upgrade to a paid instance ($7/mo) for anything real, or back up with `pg_dump`.
- **Single instance:** rate limiting is in-memory, which is correct for one instance. If you scale to multiple instances, point the limiter at Redis (`storage_uri` in `rate_limit.py`).

## Troubleshooting

- **`sslmode` / SSL connection errors:** if the Postgres URL includes `?sslmode=...`, asyncpg won't parse it. Use Render's *internal* connection string (the Blueprint already does via `fromDatabase`), which omits it.
- **Migration fails on deploy:** check the deploy logs; run `alembic upgrade head` locally against the same `DATABASE_URL` to reproduce.
