from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.routes import router
from auth import require_api_key
from rate_limit import limiter
from services.repository import repository

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist on startup. In production this is a no-op because
    # Alembic owns the schema, but it keeps local/dev runs zero-config.
    await repository.create_all()
    yield


app = FastAPI(
    title="LLM Evaluation API",
    description=(
        "Eval-as-a-Service: evaluate LLM responses for toxicity, "
        "hallucination, and brand safety before your customers find the problems."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Rate limiting (slowapi): register the limiter and its 429 handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# All /api/v1 routes require a valid bearer API key. /health and / stay public.
app.include_router(
    router,
    prefix="/api/v1",
    tags=["evaluation"],
    dependencies=[Depends(require_api_key)],
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", include_in_schema=False)
async def dashboard() -> FileResponse:
    """Serve the single-page evaluation dashboard."""
    return FileResponse(STATIC_DIR / "index.html")
