"""Inline mode and callback handlers."""

from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from app.services import DigService, get_daily_bonus_service, get_achievement_service
from app.utils.formatting import format_kg, format_duration
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# Inline mode - allows digging from any chat
@router.inline_query()
async def inline_query_handler(query: InlineQuery, dig_service: DigService):
    user_id = query.from_user.id

    # Get user stats for inline display
    from app.database import Database
    db: Database = query.bot.db if hasattr(query.bot, 'db') else None
    if not db:
        return

    user = await db.get_user_by_tg_id(user_id)
    total_kg = user.total_kg if user else 0
    username = user.username if user else "Unknown"

    # Check cooldown
    can_dig = True
    cooldown_text = ""
    if user and user.last_dig_time:
        import time
        elapsed = time.time() - user.last_dig_time
        settings = query.bot.settings if hasattr(query.bot, 'settings') else None
        if settings and elapsed < settings.dig_cooldown_seconds:
            can_dig = False
            remaining = int(settings.dig_cooldown_seconds - elapsed)
            cooldown_text = f" ⏳ {format_duration(remaining)}"

    results = []

    if can_dig:
        results.append(
            InlineQueryResultArticle(
                id="dig",
                title="🥔 Копай картошку!",
                description=f"Твой вес: {format_kg(total_kg)} кг{cooldown_text}",
                input_message_content=InputTextMessageContent(
                    message_text="🥔 Копнул картошку через inline!",
                    parse_mode="HTML",
                ),
                thumb_url="https://cdn-icons-png.flaticon.com/512/2965/2965582.png",
            )
        )
    else:
        results.append(
            InlineQueryResultArticle(
                id="cooldown",
                title="⏳ На кулдауне",
                description=f"Подожди{cooldown_text}",
                input_message_content=InputTextMessageContent(
                    message_text="⏳ Ещё не время копать!",
                ),
            )
        )

    # Stats button
    results.append(
        InlineQueryResultArticle(
            id="stats",
            title="📊 Моя статистика",
            description=f"Вес: {format_kg(total_kg)} кг",
            input_message_content=InputTextMessageContent(
                message_text=f"📊 @{username}: {format_kg(total_kg)} кг картошки",
            ),
        )
    )

    # Daily bonus
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = db
    bonus_status = await daily_bonus_service.get_status(user_id)

    if bonus_status["can_claim"]:
        results.append(
            InlineQueryResultArticle(
                id="daily",
                title="🎁 Ежедневный бонус",
                description=f"Стрик: {bonus_status['streak']} дн. — Забрать!",
                input_message_content=InputTextMessageContent(
                    message_text="🎁 Получил ежедневный бонус!",
                ),
            )
        )

    await query.answer(results, cache_time=1, is_personal=True)


# Callback query handlers for interactive buttons
@router.callback_query(F.data == "dig_now")
async def callback_dig(callback: CallbackQuery, dig_service: DigService):
    """Handle 'Dig now' button press."""
    result = await dig_service.perform_dig(
        callback.from_user.id,
        callback.from_user.username,
    )

    # Check achievements
    achievement_service = get_achievement_service()
    context = {
        "digs_count": result.get("digs_count", 1),
        "total_kg": result["total_kg"],
        "last_kg": result["kg"],
        "hour": __import__("datetime").datetime.now().hour,
    }
    unlocked = await achievement_service.check_and_unlock(callback.from_user.id, context)

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

    # Update message with new keyboard
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="show_stats")
    kb.button(text="🏆 Топ за сутки", callback_data="show_top_day")
    kb.button(text="🎁 Ежедневный бонус", callback_data="show_daily")
    kb.adjust(2, 1)

    await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "show_stats")
async def callback_stats(callback: CallbackQuery):
    """Show user stats."""
    from app.database import Database
    db: Database = callback.bot.db
    user = await db.get_user_by_tg_id(callback.from_user.id)

    if not user:
        await callback.answer("Ты еще не копаешь!", show_alert=True)
        return

    dig_service = callback.bot.dig_service
    history = await dig_service.get_user_history(callback.from_user.id, 5)
    recent = "\n".join([f"  🥔 {format_kg(h.kg)} кг" for h in history[:3]]) if history else "  (пусто)"

    # Daily bonus status
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = db
    bonus_status = await daily_bonus_service.get_status(callback.from_user.id)

    bonus_text = ""
    if bonus_status["can_claim"]:
        bonus_text = "\n🎁 <b>Ежедневный бонус доступен!</b>"
    elif bonus_status["streak"] > 0:
        bonus_text = f"\n🎁 Ежедневный бонус через: {format_duration(bonus_status['remaining_seconds'])} (стрик: {bonus_status['streak']} дн.)"

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копнуть", callback_data="dig_now")
    kb.button(text="🏆 Топ за сутки", callback_data="show_top_day")
    kb.button(text="🎁 Бонус", callback_data="show_daily")
    kb.adjust(2, 1)

    await callback.message.edit_text(
        f"📊 <b>Твоя статистика</b>\n\n"
        f"👤 @{user.username or 'без username'}\n"
        f"🥔 Всего выкопано: <b>{format_kg(user.total_kg)} кг</b>\n"
        f"📝 Последние копа:\n{recent}"
        f"{bonus_text}",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "show_top_day")
async def callback_top_day(callback: CallbackQuery):
    """Show top day leaderboard."""
    dig_service = callback.bot.dig_service
    top = await dig_service.get_top_day(10)

    if not top:
        await callback.answer("Пока никто не копает!", show_alert=True)
        return

    lines = ["🏆 <b>Топ за сутки</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копнуть", callback_data="dig_now")
    kb.button(text="📊 Статистика", callback_data="show_stats")
    kb.button(text="🏆 Общий топ", callback_data="show_top_all")
    kb.adjust(2, 1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "show_top_all")
async def callback_top_all(callback: CallbackQuery):
    """Show all-time leaderboard."""
    dig_service = callback.bot.dig_service
    top = await dig_service.get_top_all(10)

    if not top:
        await callback.answer("Пока никто не копает!", show_alert=True)
        return

    lines = ["🏆 <b>Общий топ</b>\n"]
    for entry in top:
        medal = "🥇" if entry.rank == 1 else "🥈" if entry.rank == 2 else "🥉" if entry.rank == 3 else f"{entry.rank}."
        lines.append(f"{medal} @{entry.username} — {format_kg(entry.total_kg)} кг ({entry.digs_count} копа)")

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копнуть", callback_data="dig_now")
    kb.button(text="📊 Статистика", callback_data="show_stats")
    kb.button(text="🏆 Топ за сутки", callback_data="show_top_day")
    kb.adjust(2, 1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "show_daily")
async def callback_daily(callback: CallbackQuery):
    """Show daily bonus status."""
    from app.database import Database
    db: Database = callback.bot.db

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = db
    bonus_status = await daily_bonus_service.get_status(callback.from_user.id)

    if bonus_status["can_claim"]:
        # Claim it
        result = await daily_bonus_service.claim(callback.from_user.id)
        if result["success"]:
            msg = result["message"]
        else:
            msg = f"❌ {result['error']}"
    else:
        remaining = format_duration(bonus_status["remaining_seconds"])
        msg = (
            f"🎁 <b>Ежедневный бонус</b>\n\n"
            f"🔥 Стрик: {bonus_status['streak']} дн.\n"
            f"⏰ Следующий бонус через: {remaining}"
        )

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копнуть", callback_data="dig_now")
    kb.button(text="📊 Статистика", callback_data="show_stats")
    kb.button(text="🏆 Топ за сутки", callback_data="show_top_day")
    kb.adjust(2, 1)

    await callback.message.edit_text(msg, parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "show_achievements")
async def callback_achievements(callback: CallbackQuery):
    """Show achievements."""
    achievement_service = get_achievement_service()
    user_achievements = await achievement_service.get_user_achievements(callback.from_user.id)
    all_achievements = achievement_service.get_all_achievements()

    unlocked_count = len(user_achievements)
    total_count = len(all_achievements)

    lines = [f"🏅 <b>Твои достижения</b> ({unlocked_count}/{total_count})\n"]

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

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копнуть", callback_data="dig_now")
    kb.button(text="📊 Статистика", callback_data="show_stats")
    kb.adjust(2)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()