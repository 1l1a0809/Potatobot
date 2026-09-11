"""Rate limiting middleware."""

import time
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Message
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self):
        settings = get_settings()
        self.max_requests = settings.rate_limit_requests
        self.window = settings.rate_limit_window
        self.requests: dict[int, list[float]] = defaultdict(list)

    async def __call__(self, handler, event: Message, data):
        user_id = event.from_user.id
        now = time.time()

        # Clean old requests
        self.requests[user_id] = [
            ts for ts in self.requests[user_id] if now - ts < self.window
        ]

        if len(self.requests[user_id]) >= self.max_requests:
            logger.warning("rate_limit_exceeded", user_id=user_id)
            await event.answer("⏳ Слишком много запросов. Подожди немного.")
            return

        self.requests[user_id].append(now)
        return await handler(event, data)