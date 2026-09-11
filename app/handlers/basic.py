"""Basic command handlers."""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "🥔 <b>Добро пожаловать в Potatobot!</b>\n\n"
        "Копаем картошку, соревнуемся в топе.\n\n"
        "<b>Команды:</b>\n"
        "🥔 /dig — выкопать картошку\n"
        "📊 /my_stats — твоя статистика\n"
        "📜 /my_history — история копок\n"
        "🏆 /top_day — топ за сутки\n"
        "🏆 /top_all — общий топ\n"
        "❓ /help — помощь",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "🥔 <b>Potatobot — справка</b>\n\n"
        "<b>Как играть:</b>\n"
        "1. Нажми /dig — получишь случайную картошку (1-7 кг)\n"
        "2. Копать можно раз в час\n"
        "3. Картошка накапливается в твоем общем весе\n"
        "4. Сравнивайся с другими в /top_day и /top_all\n\n"
        "<b>Команды:</b>\n"
        "🥔 /dig — выкопать картошку (раз в час)\n"
        "📊 /my_stats — твоя статистика\n"
        "📜 /my_history — последние 10 копок\n"
        "🏆 /top_day — топ-10 за сутки\n"
        "🏆 /top_all — общий топ-10\n"
        "❓ /help — эта справка",
        parse_mode="HTML",
    )