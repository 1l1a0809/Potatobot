"""Web App handlers for Telegram."""

from aiogram import Router
from aiogram.types import Message, WebAppInfo
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("app"))
async def webapp_handler(message: Message):
    """Open the Web App."""
    # Replace with your actual Web App URL
    webapp_url = "https://potatobot.app"  # Configure in env

    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Открыть ферму", web_app=WebAppInfo(url=webapp_url))

    await message.answer(
        "🥔 <b>Potatobot Web App</b>\n\n"
        "Полноценное приложение с графиками, инвентарём и достижениями!",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )