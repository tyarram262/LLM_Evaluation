import json
import logging
import sys

from config import settings

# Extra fields we promote from `logger.info(..., extra={...})` into the JSON line.
_EXTRA_FIELDS = (
    "event",
    "request_id",
    "method",
    "path",
    "status_code",
    "latency_ms",
    "app_id",
    "model",
    "prompt_tokens",
    "output_tokens",
    "total_tokens",
    "cost_usd",
)


class JsonFormatter(logging.Formatter):
    """Render each log record as a single JSON line — ideal for log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            if field in record.__dict__:
                payload[field] = record.__dict__[field]
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
    # Uvicorn's access logs would duplicate our request middleware logging.
    logging.getLogger("uvicorn.access").handlers = []


def setup_sentry() -> None:
    """Initialise Sentry only if a DSN is configured — a no-op otherwise."""
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=0.1,
        environment="production",
    )
