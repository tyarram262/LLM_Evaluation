import os
import tempfile

# Point the repository at a throwaway DB BEFORE the app (and its config) import.
# pytest loads conftest.py before collecting test modules, so this env var is set
# in time for Settings() to pick it up. Uses the async SQLite (aiosqlite) driver.
_TEST_DB = os.path.join(tempfile.gettempdir(), "test_evaluations.db")
if os.path.exists(_TEST_DB):
    os.remove(_TEST_DB)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"

# Known API key + a generous rate limit so the auth tests are deterministic.
os.environ["API_KEYS"] = "test-key"
os.environ["RATE_LIMIT"] = "1000/minute"
