"""Command handlers for digging, daily bonus, and achievements."""

from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from app.services import DigService, get_daily_bonus_service, get_achievement_service
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

    # Check achievements
    achievement_service = get_achievement_service()
    context = {
        "digs_count": 1,  # Will be updated by service
        "total_kg": result["total_kg"],
        "last_kg": result["kg"],
        "hour": datetime.now().hour,
    }
    unlocked = await achievement_service.check_and_unlock(message.from_user.id, context)

    msg = (
        f"🥔 Ты выкопал картошку весом <b>{format_kg(result['kg'])} кг</b>!\n"
        f"📦 Всего: <b>{format_kg(result['total_kg'])} кг</b>\n"
        f"⏳ Следующая копка через: <b>{format_duration(result['remaining_cooldown'])}</b>"
    )

    if unlocked:
        for ach_id in unlocked:
            ach = achievement_service.get_achievement(ach_id)
            if ach:
                msg += f"\n\n🏅 <b>Новое достижение:</b> {ach.icon} {ach.name}"

    await message.answer(msg, parse_mode="HTML")


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

    # Daily bonus status
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = db
    bonus_status = await daily_bonus_service.get_status(message.from_user.id)

    bonus_text = ""
    if bonus_status["can_claim"]:
        bonus_text = "\n🎁 <b>Ежедневный бонус доступен!</b> /daily"
    elif bonus_status["streak"] > 0:
        remaining = format_duration(bonus_status["remaining_seconds"])
        bonus_text = f"\n🎁 Ежедневный бонус через: {remaining} (стрик: {bonus_status['streak']} дн.)"

    await message.answer(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"👤 @{user.username or 'без username'}\n"
        f"🥔 Всего выкопано: <b>{format_kg(user.total_kg)} кг</b>\n"
        f"📝 Последние копа:\n{recent}"
        f"{bonus_text}",
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


# Daily bonus handlers
@router.message(Command("daily"))
async def daily_bonus_handler(message: Message):
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = message.bot.db
    result = await daily_bonus_service.claim(message.from_user.id)

    if result["success"]:
        await message.answer(result["message"], parse_mode="HTML")
    else:
        status = await daily_bonus_service.get_status(message.from_user.id)
        remaining = format_duration(status["remaining_seconds"])
        await message.answer(
            f"⏳ <b>Бонус уже получен сегодня</b>\n\n"
            f"🔥 Стрик: {status['streak']} дн.\n"
            f"⏰ Следующий бонус через: {remaining}",
            parse_mode="HTML",
        )


# Achievements handlers
@router.message(Command("achievements"))
async def achievements_handler(message: Message):
    achievement_service = get_achievement_service()
    user_achievements = await achievement_service.get_user_achievements(message.from_user.id)
    all_achievements = achievement_service.get_all_achievements()

    unlocked_count = len(user_achievements)
    total_count = len(all_achievements)

    lines = [
        f"🏅 <b>Твои достижения</b> ({unlocked_count}/{total_count})\n",
    ]

    # Group by category
    categories = {
        "🥔 Копание": ["first_dig", "dig_10", "dig_100", "dig_1000"],
        "📦 Вес": ["weight_10", "weight_100", "weight_1000"],
        "🔥 Стрики": ["streak_3", "streak_7", "streak_14", "streak_30"],
        "🏆 Топы": ["top_day_1", "top_day_3", "top_all_1"],
        "✨ Специальные": ["big_potato", "night_owl", "early_bird"],
    }

    for cat_name, ach_ids in categories.items():
        lines.append(f"\n<b>{cat_name}:</b>")
        for ach_id in ach_ids:
            ach = achievement_service.get_achievement(ach_id)
            if ach_id in user_achievements:
                lines.append(f"  {ach.icon} <b>{ach.name}</b> — {ach.description}")
            else:
                lines.append(f"  🔒 <i>{ach.name}</i> — {ach.description}")

    await message.answer("\n".join(lines), parse_mode="HTML")