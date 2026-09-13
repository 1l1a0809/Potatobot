"""Command handlers: basic, dig, stats, webapp."""

import time
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.config import get_settings
from app.utils.logging import get_logger
from app.utils.validators import validate_username
from app.utils.formatting import format_kg, format_duration
from app.services import get_daily_bonus_service, get_achievement_service, get_clan_service, get_dig_service, get_ml_service

router = Router()
logger = get_logger(__name__)
settings = get_settings()


# ===== Basic handlers =====

@router.message(Command("start"))
async def start_handler(message: Message):
    user = await message.bot.db.get_or_create_user(
        message.from_user.id,
        validate_username(message.from_user.username)
    )

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = message.bot.db
    daily_status = await daily_bonus_service.get_status(message.from_user.id)

    clan_service = get_clan_service(message.bot.db)
    clan = await clan_service.get_user_clan(user.user_id)

    lines = [
        "🥔 <b>Добро пожаловать на Литовскую картофельную ферму!</b>\n",
        f"👋 Привет, {message.from_user.first_name}!\n",
        f"🥔 Твой текущий вес: <b>{format_kg(user.total_kg)} кг</b>",
        f"⛏ Всего копок: <b>{user.digs_count if hasattr(user, 'digs_count') else '?'}</b>",
    ]

    if daily_status.get("can_claim"):
        lines.append("🎁 <b>Ежедневный бонус доступен!</b> Нажми /daily")
    elif daily_status.get("streak", 0) > 0:
        lines.append(f"🔥 Стрик: <b>{daily_status['streak']} дн.</b>")

    if clan:
        lines.append(f"🏷 Клан: <b>{clan.name}</b> [{clan.tag}]")

    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копать", callback_data="dig")
    kb.button(text="📊 Статистика", callback_data="stats")
    kb.button(text="🎁 Бонус", callback_data="daily")
    kb.button(text="🌐 Веб-приложение", web_app=dict(url=f"{settings.webapp_url}"))
    kb.adjust(2, 2)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(Command("help"))
async def help_handler(message: Message):
    lines = [
        "❓ <b>Помощь</b>\n",
        "<b>Основные команды:</b>",
        "/start — Начать / перезапустить",
        "/dig — Выкопать картошку (кд 1 час)",
        "/my_stats — Моя статистика",
        "/my_history — История копок",
        "/top_day — Топ за сутки",
        "/top_all — Общий топ",
        "/daily — Ежедневный бонус",
        "/achievements — Достижения",
        "/app — Веб-приложение",
        "",
        "<b>Кланы:</b>",
        "/clan — Мой клан",
        "/clan_create — Создать клан",
        "/clan_invite — Пригласить в клан",
        "/clan_invites — Входящие приглашения",
        "/clan_top — Топ кланов",
        "/clan_transfer — Передать владение кланом",
        "",
        "<b>Рекомендации:</b>",
        "/recommend — Персональные рекомендации",
        "",
        "🥔 Копай, собирай достижения, объединяйся в кланы!"
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "stats")
async def stats_callback(callback: CallbackQuery):
    await stats_handler(callback.message, callback.from_user.id)


# ===== Dig handlers =====

@router.message(Command("dig"))
@router.callback_query(F.data == "dig")
async def dig_handler(event: Message | CallbackQuery):
    user_id = event.from_user.id
    message = event if isinstance(event, Message) else event.message

    dig_service = get_dig_service()
    dig_service.db = message.bot.db

    username = validate_username(event.from_user.username)

    try:
        result = await dig_service.perform_dig(user_id, username)
    except Exception as e:
        logger.error("dig_error", user_id=user_id, error=str(e))
        if isinstance(event, CallbackQuery):
            await event.answer("💥 Ошибка при копке", show_alert=True)
        else:
            await message.answer("💥 Ошибка при копке. Попробуй позже.")
        return

    if isinstance(event, CallbackQuery):
        await event.answer(f"🥔 Выкопано {result['kg']} кг!")

    # Maybe send recommendation (10% chance)
    if random.random() < 0.1:
        ml_service = get_ml_service(message.bot.db)
        recs = await ml_service.get_cached_recommendations(user_id)
        if recs:
            rec = recs[0]
            try:
                await message.bot.send_message(
                    user_id,
                    f"🤖 <b>Умный совет:</b>\n\n{rec.title}\n{rec.description}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    # Smart notification check
    ml_service = get_ml_service(message.bot.db)
    await ml_service.send_smart_notification(message.bot, user_id)

    lines = [
        f"🥔 <b>Выкопано: {result['kg']} кг!</b>",
        f"📦 Всего: <b>{format_kg(result['total_kg'])} кг</b>",
    ]

    if result.get("achievements"):
        for ach in result["achievements"]:
            lines.append(f"🏅 <b>Новое достижение:</b> {ach['icon']} {ach['name']}")

    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копать снова", callback_data="dig")
    kb.button(text="📊 Статистика", callback_data="stats")
    kb.adjust(2)

    if isinstance(event, CallbackQuery):
        await message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


# ===== Stats handlers =====

@router.message(Command("my_stats"))
async def stats_handler(message: Message, user_id: int | None = None):
    user_id = user_id or message.from_user.id
    user = await message.bot.db.get_user_by_tg_id(user_id)

    if not user:
        await message.answer("❌ Пользователь не найден. Попробуй /start")
        return

    dig_service = get_dig_service()
    dig_service.db = message.bot.db
    history = await dig_service.get_user_history(user_id, limit=5)

    lines = [
        "📊 <b>Твоя статистика</b>\n",
        f"🥔 Всего картошки: <b>{format_kg(user.total_kg)} кг</b>",
        f"⛏ Копок: <b>{user.digs_count if hasattr(user, 'digs_count') else len(history)}</b>",
    ]

    if history:
        lines.append("\n📜 <b>Последние копки:</b>")
        for h in history:
            lines.append(f"  🥔 {format_kg(h.kg)} кг — {time.strftime('%d.%m %H:%M', time.localtime(h.timestamp))}")

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = message.bot.db
    daily_status = await daily_bonus_service.get_status(user_id)
    if daily_status.get("streak", 0) > 0:
        lines.append(f"\n🔥 Стрик: <b>{daily_status['streak']} дн.</b>")

    achievement_service = get_achievement_service()
    user_achievements = await achievement_service.get_user_achievements(user.user_id)
    lines.append(f"🏅 Достижений: <b>{len(user_achievements)}</b>")

    clan_service = get_clan_service(message.bot.db)
    clan = await clan_service.get_user_clan(user.user_id)
    if clan:
        lines.append(f"🏷 Клан: <b>{clan.name}</b> [{clan.tag}]")

    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копать", callback_data="dig")
    kb.button(text="📜 История", callback_data="history")
    kb.button(text="🏅 Достижения", callback_data="achievements")
    kb.adjust(3)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.message(Command("my_history"))
async def history_handler(message: Message):
    dig_service = get_dig_service()
    dig_service.db = message.bot.db
    history = await dig_service.get_user_history(message.from_user.id, limit=20)

    if not history:
        await message.answer("📜 История пуста. Начни копать /dig!")
        return

    lines = ["📜 <b>История копок (последние 20)</b>\n"]
    for h in history:
        lines.append(f"🥔 {format_kg(h.kg)} кг — {time.strftime('%d.%m.%Y %H:%M', time.localtime(h.timestamp))}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("top_day"))
async def top_day_handler(message: Message):
    db = message.bot.db
    rows = await db.get_top_day(10)

    if not rows:
        await message.answer("🏆 Топ за сутки пуст. Стань первым!")
        return

    lines = ["🏆 <b>Топ за сутки</b>\n"]
    for e in rows:
        lines.append(f"{e.rank}. {e.username} — {format_kg(e.total_kg)} кг ({e.digs_count} копок)")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("top_all"))
async def top_all_handler(message: Message):
    db = message.bot.db
    rows = await db.get_top_all(10)

    if not rows:
        await message.answer("🏆 Общий топ пуст. Стань первым!")
        return

    lines = ["🏆 <b>Общий топ</b>\n"]
    for e in rows:
        lines.append(f"{e.rank}. {e.username} — {format_kg(e.total_kg)} кг ({e.digs_count} копок)")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "history")
async def history_callback(callback: CallbackQuery):
    await history_handler(callback.message)


@router.callback_query(F.data == "achievements")
async def achievements_callback(callback: CallbackQuery):
    from app.handlers.features import achievements_handler
    await achievements_handler(callback.message)


# ===== Daily bonus handlers =====

@router.message(Command("daily"))
@router.callback_query(F.data == "daily")
async def daily_handler(event: Message | CallbackQuery):
    user_id = event.from_user.id
    message = event if isinstance(event, Message) else event.message

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = message.bot.db

    status = await daily_bonus_service.get_status(user_id)

    if status.get("can_claim"):
        result = await daily_bonus_service.claim(user_id)
        lines = [
            f"🎁 <b>Ежедневный бонус получен!</b>",
            f"🥔 +{result['kg']} кг",
            f"🔥 Стрик: <b>{result['streak']} дн.</b>",
            f"📦 Всего: <b>{format_kg(result['total_kg'])} кг</b>",
        ]
        if result.get("achievements"):
            for ach in result["achievements"]:
                lines.append(f"🏅 <b>Новое достижение:</b> {ach['icon']} {ach['name']}")
    else:
        wait_time = status.get("wait_seconds", 0)
        lines = [
            "🎁 <b>Ежедневный бонус</b>",
            f"🔥 Текущий стрик: <b>{status.get('streak', 0)} дн.</b>",
            f"⏳ Следующий бонус через: <b>{format_duration(wait_time)}</b>",
            f"🥔 Базовый бонус: {format_kg(settings.daily_bonus_base_kg)} кг",
        ]

    kb = InlineKeyboardBuilder()
    kb.button(text="🥔 Копать", callback_data="dig")
    kb.button(text="📊 Статистика", callback_data="stats")
    kb.adjust(2)

    if isinstance(event, CallbackQuery):
        await message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    else:
        await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


# ===== Achievements handlers =====

@router.message(Command("achievements"))
async def achievements_handler(message: Message):
    achievement_service = get_achievement_service()
    user = await message.bot.db.get_user_by_tg_id(message.from_user.id)

    if not user:
        await message.answer("❌ Пользователь не найден. Попробуй /start")
        return

    user_achievements = await achievement_service.get_user_achievements(user.user_id)
    all_achievements = achievement_service.get_all_achievements()

    lines = ["🏅 <b>Достижения</b>\n"]
    for ach in all_achievements:
        unlocked = ach.id in user_achievements
        icon = ach.icon if unlocked else "🔒"
        lines.append(f"{icon} <b>{ach.name}</b> — {ach.description}")

    lines.append(f"\n📊 Разблокировано: <b>{len(user_achievements)}/{len(all_achievements)}</b>")

    await message.answer("\n".join(lines), parse_mode="HTML")


# ===== WebApp handlers =====

@router.message(Command("app"))
async def webapp_handler(message: Message):
    from aiogram.types import WebAppInfo
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Открыть веб-приложение", web_app=WebAppInfo(url=settings.webapp_url))
    await message.answer(
        "🌐 <b>Веб-приложение</b>\n\n"
        "Открой для удобного управления фермой, просмотра статистики и кланов.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )