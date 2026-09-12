"""Handlers package."""

from app.handlers.basic import router as basic_router
from app.handlers.dig import router as dig_router
from app.handlers.stats import router as stats_router
from app.handlers.webapp import router as webapp_router
from app.handlers.inline import router as inline_router

__all__ = ["basic_router", "dig_router", "stats_router", "webapp_router", "inline_router"]