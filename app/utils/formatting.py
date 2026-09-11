"""Formatting utilities."""

from app.config import get_settings


def format_kg(kg: float) -> str:
    settings = get_settings()
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