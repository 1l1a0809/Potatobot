"""ML Recommendations handlers."""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services import get_ml_service, get_clan_service
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(Command("recommend"))
async def recommend_handler(message: Message):
    """Get personalized recommendations."""
    ml_service = get_ml_service(message.bot.db)
    recommendations = await ml_service.get_cached_recommendations(message.from_user.id)

    if not recommendations:
        await message.answer(
            "🤖 <b>Персональные рекомендации</b>\n\n"
            "Пока не хватает данных для рекомендаций.\n"
            "Начни копать (/dig) и забирай бонусы (/daily)!\n\n"
            "Через несколько дней появится анализ твоего стиля игры.",
            parse_mode="HTML",
        )
        return

    lines = ["🤖 <b>Персональные рекомендации</b>\n"]

    for i, rec in enumerate(recommendations, 1):
        priority_emoji = "🔥" if rec.priority >= 8 else "⭐" if rec.priority >= 5 else "💡"
        lines.append(
            f"{i}. {priority_emoji} <b>{rec.title}</b>\n"
            f"   {rec.description}\n"
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="recommend_refresh")
    kb.button(text="📊 Профиль", callback_data="recommend_profile")
    kb.adjust(2)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "recommend_refresh")
async def recommend_refresh_callback(callback: CallbackQuery):
    ml_service = get_ml_service(callback.bot.db)
    await ml_service.invalidate_cache(callback.from_user.id)
    recommendations = await ml_service.generate_recommendations(callback.from_user.id)

    if not recommendations:
        await callback.answer("Недостаточно данных", show_alert=True)
        return

    lines = ["🤖 <b>Персональные рекомендации</b> (обновлено)\n"]
    for i, rec in enumerate(recommendations, 1):
        priority_emoji = "🔥" if rec.priority >= 8 else "⭐" if rec.priority >= 5 else "💡"
        lines.append(
            f"{i}. {priority_emoji} <b>{rec.title}</b>\n"
            f"   {rec.description}\n"
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="recommend_refresh")
    kb.button(text="📊 Профиль", callback_data="recommend_profile")
    kb.adjust(2)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer("Обновлено!")


@router.callback_query(F.data == "recommend_profile")
async def recommend_profile_callback(callback: CallbackQuery):
    from app.services import get_ml_service
    ml_service = get_ml_service(callback.bot.db)
    profile = await ml_service.get_user_profile(callback.from_user.id)

    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    from app.utils.formatting import format_kg
    from app.services import get_clan_service
    clan_service = get_clan_service(callback.bot.db)
    clan = await clan_service.get_clan(profile.clan_id) if profile.clan_id else None

    lines = [
        "📊 <b>Твой профиль</b>\n",
        f"🥔 Всего кг: <b>{format_kg(profile.total_kg)}</b>",
        f"⛏ Копок: <b>{profile.digs_count}</b>",
        f"📊 Средний вес: <b>{profile.avg_kg_per_dig:.1f} кг</b>",
        f"🔥 Стрик: <b>{profile.streak} дн.</b>",
        f"🏅 Достижений: <b>{profile.achievements_count}</b>",
    ]

    if profile.favorite_hour is not None:
        lines.append(f"⏰ Любимое время: <b>{profile.favorite_hour}:00</b>")

    if profile.favorite_day is not None:
        days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        lines.append(f"📅 Любимый день: <b>{days[profile.favorite_day]}</b>")

    if clan:
        lines.append(f"🏷 Клан: <b>{clan.name}</b> [{clan.tag}]")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 К рекомендациям", callback_data="recommend_refresh")

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


# Smart notification handler (called from other handlers)
async def send_smart_notification(bot, user_id: int):
    """Send a smart notification based on user behavior."""
    from app.services import get_ml_service
    ml_service = get_ml_service(bot.db)
    profile = await ml_service.get_user_profile(user_id)

    if not profile:
        return

    # Check if user hasn't played in 24 hours
    import time
    if time.time() - profile.last_active > 86400:
        try:
            await bot.send_message(
                user_id,
                "🥔 <b>Скучаем по тебе!</b>\n\n"
                "Давно не копали? Заходи за ежедневным бонусом /daily "
                "и продолжай набирать вес!",
                parse_mode="HTML",
            )
        except Exception:
            pass  # User blocked bot


# Integration with dig handler - send recommendation after dig
async def maybe_send_recommendation(bot, user_id: int):
    """Maybe send a recommendation after dig (10% chance)."""
    import random
    if random.random() < 0.1:
        ml_service = get_ml_service(bot.db)
        recommendations = await ml_service.get_cached_recommendations(user_id)

        if recommendations:
            rec = recommendations[0]
            try:
                await bot.send_message(
                    user_id,
                    f"🤖 <b>Умный совет:</b>\n\n"
                    f"{rec.title}\n{rec.description}",
                    parse_mode="HTML",
                )
            except Exception:
                pass