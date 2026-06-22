import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.v1.routes import router
from auth import require_api_key
from observability import setup_logging, setup_sentry
from rate_limit import limiter
from services.repository import repository

setup_logging()
setup_sentry()

STATIC_DIR = Path(__file__).parent / "static"
access_logger = logging.getLogger("api")


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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Assign a request id, time the request, and emit one structured log line."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    start = time.monotonic()
    response = await call_next(request)
    latency_ms = round((time.monotonic() - start) * 1000, 1)
    access_logger.info(
        "request",
        extra={
            "event": "http_request",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    response.headers["x-request-id"] = request_id
    return response

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
