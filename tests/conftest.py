"""Global pytest configuration ensuring storage directories and database initialization."""

import pytest
from backend.config import ensure_storage_directories
from backend.database import init_db


@pytest.fixture(scope="session", autouse=True)
def initialize_test_suite_environment():
    """Ensure all required directories and database migrations are initialized before test collection/execution."""
    ensure_storage_directories()
    init_db()

