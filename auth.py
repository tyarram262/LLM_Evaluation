from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

# auto_error=True → a missing/blank Authorization header yields 403 automatically;
# an present-but-wrong key falls through to our explicit 401 below.
_bearer = HTTPBearer(auto_error=True)


def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """FastAPI dependency: validate the bearer token against configured API keys."""
    if credentials.credentials not in settings.valid_api_keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials
