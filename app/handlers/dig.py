"""Command handlers for digging."""

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from app.services import DigService
from app.utils.formatting import format_kg, format_duration
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("dig"))
async def dig_handler(message: Message, dig_service: DigService):
    result = await dig_service.perform_dig(
        message.from_user.id,
        message.from_user.username,
    )
    await message.answer(
        f"🥔 Ты выкопал картошку весом <b>{format_kg(result['kg'])} кг</b>!\n"
        f"📦 Всего: <b>{format_kg(result['total_kg'])} кг</b>\n"
        f"⏳ Следующая копка через: <b>{format_duration(result['remaining_cooldown'])}</b>",
        parse_mode="HTML",
    )


@router.message(Command("my_stats"))
async def my_stats_handler(message: Message, dig_service: DigService):
    from app.database import Database
    from app.config import get_settings
    
    settings = get_settings()
    db: Database = message.bot.db
    user = await db.get_user_by_tg_id(message.from_user.id)
    
    if not user:
        await message.answer("❌ Ты еще не копаешь! Начни с /dig")
        return

    history = await dig_service.get_user_history(message.from_user.id, 5)
    recent = "\n".join(
        [f"  🥔 {format_kg(h.kg)} кг" for h in history[:3]]
    ) if history else "  (пусто)"

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"👤 @{user.username or 'без username'}\n"
        f"🥔 Всего выкопано: <b>{format_kg(user.total_kg)} кг</b>\n"
        f"📝 Последние копа:\n{recent}",
        parse_mode="HTML",
    )


@router.message(Command("my_history"))
async def my_history_handler(message: Message, dig_service: DigService):
    history = await dig_service.get_user_history(message.from_user.id, 10)
    
    if not history:
        await message.answer("📭 История пуста. Начни копать с /dig")
        return

    lines = [f"📜 <b>История копок</b> (последние {len(history)}):\n"]
    for i, h in enumerate(history, 1):
        from datetime import datetime
        dt = datetime.fromtimestamp(h.timestamp).strftime("%d.%m %H:%M")
        lines.append(f"{i}. {format_kg(h.kg)} кг — {dt}")
    
    await message.answer("\n".join(lines), parse_mode="HTML")