"""Utils package: cache, formatting, logging, validators."""

import structlog
import logging
import sys
import time
import re
from functools import wraps
from typing import TypeVar, Callable, Any, Optional
from app.config import get_settings

settings = get_settings()


# ===== Cache =====

T = TypeVar("T")


class TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        if key in self._cache:
            expires, value = self._cache[key]
            if time.time() < expires:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.time() + self.ttl, value)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()


def cached(ttl: int, key_prefix: str = ""):
    cache = TTLCache(ttl)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"
            if cached := cache.get(key):
                return cached
            result = await func(*args, **kwargs)
            cache.set(key, result)
            return result

        wrapper.cache = cache
        return wrapper

    return decorator


# ===== Formatting =====

def format_kg(kg: float) -> str:
    return f"{kg:.{settings.dig_precision}f}"


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes} мин {secs} сек"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} ч {mins} мин"


# ===== Logging =====

def setup_logging(level: str = "INFO", format: str = "json") -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if format == "json"
            else structlog.dev.ConsoleRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str = None):
    """Get structured logger."""
    return structlog.get_logger(name)


# ===== Validators =====

def validate_username(username: str | None) -> str | None:
    """Validate and sanitize Telegram username."""
    if username is None:
        return None
    # Telegram usernames: 5-32 chars, alphanumeric + underscore
    username = username.strip()
    if not username:
        return None
    if len(username) > 32:
        username = username[:32]
    # Remove @ if present
    if username.startswith("@"):
        username = username[1:]
    # Validate characters
    if not re.match(r"^[A-Za-z0-9_]+$", username):
        return None
    return username


def validate_dig_amount(kg: float) -> float:
    """Validate dig amount is within bounds."""
    if kg < settings.dig_min_kg:
        return settings.dig_min_kg
    if kg > settings.dig_max_kg:
        return settings.dig_max_kg
    return round(kg, settings.dig_precision)


__all__ = [
    "TTLCache",
    "cached",
    "format_kg",
    "format_duration",
    "setup_logging",
    "get_logger",
    "validate_username",
    "validate_dig_amount",
]