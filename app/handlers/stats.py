"""Command handlers for leaderboards."""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from app.services import DigService
from app.utils.formatting import format_kg
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("top_day"))
async def top_day_handler(message: Message, dig_service: DigService):
    top = await dig_service.get_top_day(10)
    
    if not top:
        await message.answer("📭 За сегодня никто еще не копал. Стань первым с /dig!")
        return

    lines = ["🏆 <b>Топ за сутки</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")
    
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("top_all"))
async def top_all_handler(message: Message, dig_service: DigService):
    top = await dig_service.get_top_all(10)
    
    if not top:
        await message.answer("📭 Еще никто не копает. Стань первым с /dig!")
        return

    lines = ["🏆 <b>Общий топ</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")
    
    await message.answer("\n".join(lines), parse_mode="HTML")