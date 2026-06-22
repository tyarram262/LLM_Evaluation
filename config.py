from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str = "placeholder"
    model_id: str = "gemini-2.0-flash"
    max_tokens: int = 1024
    # Per-attempt timeout (seconds) and max attempts for the judge LLM call.
    request_timeout: float = 30.0
    max_retries: int = 3
    database_url: str = "sqlite+aiosqlite:///./evaluations.db"

    # Comma-separated list of accepted client API keys (bearer tokens).
    # Always has at least one value so the API is never silently open.
    api_keys: str = "dev-local-key"
    # Per-key request limit for the expensive /evaluate endpoint.
    rate_limit: str = "60/minute"

    # Observability
    log_level: str = "INFO"
    sentry_dsn: str = ""  # set to enable Sentry error tracking

    @property
    def valid_api_keys(self) -> set[str]:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


settings = Settings()
