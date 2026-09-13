"""Middleware package: error_handling, logging, rate_limit."""

import time
from collections import defaultdict
from aiogram import BaseMiddleware
from aiogram.types import Message, ErrorEvent
from aiogram.exceptions import TelegramAPIError
from app.config import get_settings
from app.exceptions import CooldownError, ValidationError, DatabaseError, UserNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


# ===== ErrorHandlingMiddleware =====

class ErrorHandlingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except CooldownError as e:
            if isinstance(event, Message):
                mins = e.remaining // 60
                secs = e.remaining % 60
                if mins > 0:
                    await event.answer(f"⏳ Подожди {mins} мин {secs} сек до следующей копки")
                else:
                    await event.answer(f"⏳ Подожди {secs} сек до следующей копки")
        except ValidationError as e:
            if isinstance(event, Message):
                await event.answer(f"❌ {e.message}")
        except UserNotFoundError:
            if isinstance(event, Message):
                await event.answer("❌ Пользователь не найден. Попробуй /start")
        except DatabaseError:
            logger.error("database_error", exc_info=True)
            if isinstance(event, Message):
                await event.answer("🔧 Ошибка базы данных. Попробуй позже.")
        except TelegramAPIError as e:
            logger.warning("telegram_api_error", error=str(e))
        except Exception as e:
            logger.error("unhandled_error", exc_info=True)
            if isinstance(event, Message):
                await event.answer("💥 Произошла ошибка. Админы уже уведомлены.")


# ===== LoggingMiddleware =====

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data):
        logger.info(
            "command_received",
            user_id=event.from_user.id,
            username=event.from_user.username,
            command=event.text,
        )
        return await handler(event, data)


# ===== RateLimitMiddleware =====

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self):
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


__all__ = [
    "ErrorHandlingMiddleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
]