"""Logging middleware."""

from aiogram import BaseMiddleware
from aiogram.types import Message
from app.utils.logging import get_logger

logger = get_logger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        logger.info(
            "command_received",
            user_id=event.from_user.id,
            username=event.from_user.username,
            command=event.text,
        )
        return await handler(event, data)