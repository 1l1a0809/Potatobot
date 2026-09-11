"""Test configuration and fixtures."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.database import Database
from app.config import Settings


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    return Settings(
        bot_token="123456:test_token",
        database_url="postgresql://test:test@localhost:5432/test",
        db_pool_min=1,
        db_pool_max=2,
        dig_cooldown_seconds=3600,
        dig_min_kg=1.0,
        dig_max_kg=7.0,
        dig_precision=1,
        history_retention_hours=48,
        cleanup_interval_seconds=3600,
        leaderboard_cache_ttl=30,
        rate_limit_requests=30,
        rate_limit_window=60,
        web_host="0.0.0.0",
        web_port=8080,
        log_level="DEBUG",
        log_format="console",
    )


@pytest.fixture
def mock_db():
    """Mock database for unit tests."""
    db = AsyncMock(spec=Database)
    return db