from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    """Rate-limit per API key when present, otherwise fall back to client IP."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return get_remote_address(request)


# In-memory limiter. For multi-worker / horizontally-scaled production, point
# `storage_uri` at Redis (e.g. "redis://host:6379") so limits are shared.
limiter = Limiter(key_func=_rate_limit_key)
