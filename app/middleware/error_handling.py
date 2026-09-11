"""Error handling middleware."""

from aiogram import BaseMiddleware
from aiogram.types import Message, ErrorEvent
from aiogram.exceptions import TelegramAPIError
from app.exceptions import CooldownError, ValidationError, DatabaseError, UserNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)


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