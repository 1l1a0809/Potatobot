"""Command handlers for leaderboards."""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from app.services import DigService, get_achievement_service
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

    # Check top achievements for current user
    achievement_service = get_achievement_service()
    user_rank = next((i + 1 for i, e in enumerate(top) if e.username == (message.from_user.username or f"User_{message.from_user.id}")), None)

    if user_rank == 1:
        await achievement_service.unlock(message.from_user.id, "top_day_1")
    elif user_rank and user_rank <= 3:
        await achievement_service.unlock(message.from_user.id, "top_day_3")

    lines = ["🏆 <b>Топ за сутки</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        # Highlight current user
        if entry.username == (message.from_user.username or f"User_{message.from_user.id}"):
            lines.append(f"{medal} <b>@{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа) ← ТЫ</b>")
        else:
            lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("top_all"))
async def top_all_handler(message: Message, dig_service: DigService):
    top = await dig_service.get_top_all(10)

    if not top:
        await message.answer("📭 Еще никто не копает. Стань первым с /dig!")
        return

    # Check top_all achievement
    achievement_service = get_achievement_service()
    user_rank = next((i + 1 for i, e in enumerate(top) if e.username == (message.from_user.username or f"User_{message.from_user.id}")), None)

    if user_rank == 1:
        await achievement_service.unlock(message.from_user.id, "top_all_1")

    lines = ["🏆 <b>Общий топ</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        if entry.username == (message.from_user.username or f"User_{message.from_user.id}"):
            lines.append(f"{medal} <b>@{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа) ← ТЫ</b>")
        else:
            lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")

    await message.answer("\n".join(lines), parse_mode="HTML")