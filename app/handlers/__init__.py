"""Handlers package."""

from app.handlers.commands import router as commands_router
from app.handlers.features import router as features_router

__all__ = [
    "commands_router", "features_router",
]