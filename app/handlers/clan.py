"""Clan command handlers."""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services import DigService, get_clan_service
from app.utils.formatting import format_kg, format_duration
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# Clan creation
@router.message(Command("clan_create"))
async def clan_create_handler(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "❌ Использование: <code>/clan_create Название Тег [Описание]</code>\n\n"
            "Пример: <code>/clan_create \"Картошные фермеры\" KF Наш дружный клан</code>",
            parse_mode="HTML",
        )
        return

    name = args[1].strip('"')
    tag = args[2].upper()
    description = args[3] if len(args) > 3 else ""

    clan_service = get_clan_service(message.bot.db)
    result = await clan_service.create_clan(message.from_user.id, name, tag, description)

    if result["success"]:
        await message.answer(
            f"✅ <b>Клан создан!</b>\n\n"
            f"🏷 Название: <b>{name}</b>\n"
            f"🏷 Тег: <b>{tag}</b>\n"
            f"👑 Владелец: @{message.from_user.username or 'ты'}\n"
            f"📝 Описание: {description or '—'}\n\n"
            f"Пригласи друзей: <code>/clan_invite @username</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"❌ {result['error']}", parse_mode="HTML")


# Clan info
@router.message(Command("clan"))
async def clan_info_handler(message: Message):
    clan_service = get_clan_service(message.bot.db)
    clan = await clan_service.get_user_clan(message.from_user.id)

    if not clan:
        await message.answer(
            "🏷 <b>Ты не в клане</b>\n\n"
            "Создай свой: <code>/clan_create Название Тег</code>\n"
            "Или попроси приглашение у друга.",
            parse_mode="HTML",
        )
        return

    members = await clan_service.get_clan_members(clan.clan_id)

    lines = [
        f"🏷 <b>{clan.name}</b> [{clan.tag}]\n"
        f"👑 Владелец: @{await _get_username(message.bot.db, clan.owner_id)}\n"
        f"🥔 Всего кг: <b>{format_kg(clan.total_kg)}</b>\n"
        f"👥 Участников: <b>{clan.member_count}</b>\n"
        f"📝 {clan.description or 'Описания нет'}\n",
    ]

    lines.append("<b>Участники:</b>")
    for i, member in enumerate(members[:10], 1):
        role_emoji = {"owner": "👑", "officer": "⭐", "member": "👤"}.get(member.role, "👤")
        username = await _get_username(message.bot.db, member.user_id)
        lines.append(
            f"{i}. {role_emoji} @{username} — {format_kg(member.contributed_kg)} кг"
        )

    if len(members) > 10:
        lines.append(f"\n... и ещё {len(members) - 10} участников")

    kb = InlineKeyboardBuilder()
    if clan.owner_id == message.from_user.id:
        kb.button(text="⚙️ Управление", callback_data="clan_manage")
    kb.button(text="📨 Пригласить", callback_data="clan_invite")
    kb.button(text="🚪 Покинуть", callback_data="clan_leave")
    kb.adjust(2, 1)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


async def _get_username(db, user_id: int) -> str:
    user = await db.get_user_by_tg_id(user_id)
    return user.username if user else f"user_{user_id}"


# Clan invites
@router.message(Command("clan_invite"))
async def clan_invite_handler(message: Message):
    clan_service = get_clan_service(message.bot.db)
    clan = await clan_service.get_user_clan(message.from_user.id)

    if not clan:
        await message.answer("❌ Ты не в клане")
        return

    member = await clan_service.get_member(clan.clan_id, message.from_user.id)
    if not member or member.role not in ("owner", "officer"):
        await message.answer("❌ Нет прав на приглашение")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: <code>/clan_invite @username</code>", parse_mode="HTML")
        return

    username = args[1].lstrip("@")
    result = await clan_service.invite_user(message.from_user.id, username)

    if result["success"]:
        await message.answer(f"✅ Приглашение отправлено @{username}!")
    else:
        await message.answer(f"❌ {result['error']}")


@router.message(Command("clan_invites"))
async def clan_invites_handler(message: Message):
    clan_service = get_clan_service(message.bot.db)
    invites = await clan_service.get_pending_invites(message.from_user.id)

    if not invites:
        await message.answer("📭 Входящих приглашений нет")
        return

    lines = ["📨 <b>Входящие приглашения:</b>\n"]
    kb = InlineKeyboardBuilder()

    for invite in invites:
        lines.append(
            f"🏷 <b>{invite['name']}</b> [{invite['tag']}]\n"
            f"   Пригласил: @{invite['inviter_name']}\n"
            f"   Истекает: {format_duration(int(invite['expires_at'] - __import__('time').time()))}\n"
        )
        kb.button(
            text=f"✅ {invite['name']} [{invite['tag']}]",
            callback_data=f"clan_accept_{invite['invite_id']}",
        )
        kb.button(
            text=f"❌ Отклонить",
            callback_data=f"clan_decline_{invite['invite_id']}",
        )

    kb.adjust(2)
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


# Callback handlers
@router.callback_query(F.data == "clan_accept_")
async def clan_accept_callback(callback: CallbackQuery):
    invite_id = callback.data.replace("clan_accept_", "")
    clan_service = get_clan_service(callback.bot.db)
    result = await clan_service.accept_invite(callback.from_user.id, invite_id)

    if result["success"]:
        clan = await clan_service.get_clan(result["clan_id"])
        await callback.message.edit_text(
            f"✅ <b>Ты вступил в клан!</b>\n\n"
            f"🏷 {clan.name} [{clan.tag}]\n"
            f"🥔 Внесёшь свой вклад: /dig",
            parse_mode="HTML",
        )
    else:
        await callback.answer(result["error"], show_alert=True)


@router.callback_query(F.data == "clan_decline_")
async def clan_decline_callback(callback: CallbackQuery):
    invite_id = callback.data.replace("clan_decline_", "")
    clan_service = get_clan_service(callback.bot.db)
    result = await clan_service.decline_invite(callback.from_user.id, invite_id)

    if result["success"]:
        await callback.answer("Приглашение отклонено")
        await callback.message.edit_text("❌ Приглашение отклонено")
    else:
        await callback.answer(result["error"], show_alert=True)


@router.callback_query(F.data == "clan_leave")
async def clan_leave_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    result = await clan_service.leave_clan(callback.from_user.id)

    if result["success"]:
        await callback.message.edit_text("👋 Ты покинул клан")
    else:
        await callback.answer(result["error"], show_alert=True)


@router.callback_query(F.data == "clan_manage")
async def clan_manage_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    clan = await clan_service.get_user_clan(callback.from_user.id)

    if not clan or clan.owner_id != callback.from_user.id:
        await callback.answer("Только владелец может управлять", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="👑 Передать владение", callback_data="clan_transfer")
    kb.button(text="💥 Распустить клан", callback_data="clan_disband")
    kb.button(text="👥 Участники", callback_data="clan_members")
    kb.button(text="🔙 Назад", callback_data="clan_back")
    kb.adjust(2)

    await callback.message.edit_text(
        f"⚙️ <b>Управление кланом {clan.name}</b>\n\n"
        f"Выбери действие:",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "clan_back")
async def clan_back_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    clan = await clan_service.get_user_clan(callback.from_user.id)
    # Re-show clan info
    await clan_info_callback(callback)


@router.callback_query(F.data == "clan_members")
async def clan_members_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    clan = await clan_service.get_user_clan(callback.from_user.id)
    members = await clan_service.get_clan_members(clan.clan_id)

    lines = [f"👥 <b>Участники {clan.name}</b>:\n"]
    for member in members:
        role_emoji = {"owner": "👑", "officer": "⭐", "member": "👤"}.get(member.role, "👤")
        username = await _get_username(callback.bot.db, member.user_id)
        lines.append(f"{role_emoji} @{username} — {format_kg(member.contributed_kg)} кг")

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="clan_back")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "clan_transfer")
async def clan_transfer_callback(callback: CallbackQuery):
    await callback.answer(
        "Используй: <code>/clan_transfer @username</code> для передачи владения",
        show_alert=True,
    )


@router.callback_query(F.data == "clan_disband")
async def clan_disband_callback(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Да, распустить", callback_data="clan_disband_confirm")
    kb.button(text="❌ Отмена", callback_data="clan_back")
    await callback.message.edit_text(
        "⚠️ <b>Ты уверен?</b>\n\n"
        "Клан будет полностью удален со всеми участниками и статистикой.\n"
        "Это действие необратимо!",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data == "clan_disband_confirm")
async def clan_disband_confirm_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    result = await clan_service.disband_clan(callback.from_user.id)

    if result["success"]:
        await callback.message.edit_text("💥 Клан распущен")
    else:
        await callback.answer(result["error"], show_alert=True)


# Clan transfer command
@router.message(Command("clan_transfer"))
async def clan_transfer_handler(message: Message):
    clan_service = get_clan_service(message.bot.db)
    clan = await clan_service.get_user_clan(message.from_user.id)

    if not clan or clan.owner_id != message.from_user.id:
        await message.answer("❌ Ты не владелец клана")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❌ Использование: <code>/clan_transfer @username</code>", parse_mode="HTML")
        return

    username = args[1].lstrip("@")
    async with message.bot.db.acquire() as conn:
        target = await conn.fetchrow(
            "SELECT user_id FROM users WHERE LOWER(username) = LOWER($1)", username,
        )

    if not target:
        await message.answer("❌ Пользователь не найден")
        return

    result = await clan_service.transfer_ownership(message.from_user.id, target["user_id"])

    if result["success"]:
        await message.answer(f"✅ Владение передано @{username}!")
    else:
        await message.answer(f"❌ {result['error']}")


# Clan leaderboard
@router.message(Command("clan_top"))
async def clan_top_handler(message: Message):
    clan_service = get_clan_service(message.bot.db)
    top = await clan_service.get_top_clans(10)

    if not top:
        await message.answer("📭 Пока нет кланов. Создай первый: /clan_create")
        return

    lines = ["🏆 <b>Топ кланов</b>\n"]
    for clan in top:
        medal = "🥇" if clan["rank"] == 1 else "🥈" if clan["rank"] == 2 else "🥉" if clan["rank"] == 3 else f"{clan['rank']}."
        lines.append(
            f"{medal} <b>{clan['name']}</b> [{clan['tag']}] — "
            f"{format_kg(clan['total_kg'])} кг ({clan['member_count']} чел.)"
        )

    # Highlight user's clan
    clan_service = get_clan_service(message.bot.db)
    user_clan = await clan_service.get_user_clan(message.from_user.id)
    if user_clan:
        for i, clan in enumerate(top):
            if clan["clan_id"] == user_clan.clan_id:
                lines[i + 1] += " ← ТЫ"
                break

    await message.answer("\n".join(lines), parse_mode="HTML")


# Add contribution when digging (called from dig_service)
async def add_clan_contribution(bot, user_id: int, kg: float):
    clan_service = get_clan_service(bot.db)
    await clan_service.add_contribution(user_id, kg)


# Callback for clan info from inline
@router.callback_query(F.data == "clan_info")
async def clan_info_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    clan = await clan_service.get_user_clan(callback.from_user.id)

    if not clan:
        await callback.message.edit_text(
            "🏷 <b>Ты не в клане</b>\n\n"
            "Создай свой: <code>/clan_create Название Тег</code>",
            parse_mode="HTML",
        )
        return

    members = await clan_service.get_clan_members(clan.clan_id)

    lines = [
        f"🏷 <b>{clan.name}</b> [{clan.tag}]\n"
        f"👑 Владелец: @{await _get_username(callback.bot.db, clan.owner_id)}\n"
        f"🥔 Всего кг: <b>{format_kg(clan.total_kg)}</b>\n"
        f"👥 Участников: <b>{clan.member_count}</b>\n"
        f"📝 {clan.description or 'Описания нет'}\n",
    ]

    lines.append("<b>Участники:</b>")
    for i, member in enumerate(members[:10], 1):
        role_emoji = {"owner": "👑", "officer": "⭐", "member": "👤"}.get(member.role, "👤")
        username = await _get_username(callback.bot.db, member.user_id)
        lines.append(
            f"{i}. {role_emoji} @{username} — {format_kg(member.contributed_kg)} кг"
        )

    if len(members) > 10:
        lines.append(f"\n... и ещё {len(members) - 10} участников")

    kb = InlineKeyboardBuilder()
    if clan.owner_id == callback.from_user.id:
        kb.button(text="⚙️ Управление", callback_data="clan_manage")
    kb.button(text="📨 Пригласить", callback_data="clan_invite")
    kb.button(text="🚪 Покинуть", callback_data="clan_leave")
    kb.button(text="🏆 Топ кланов", callback_data="clan_top")
    kb.adjust(2, 1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


# Clan top callback
@router.callback_query(F.data == "clan_top")
async def clan_top_callback(callback: CallbackQuery):
    clan_service = get_clan_service(callback.bot.db)
    top = await clan_service.get_top_clans(10)

    if not top:
        await callback.message.edit_text("📭 Пока нет кланов")
        return

    lines = ["🏆 <b>Топ кланов</b>\n"]
    for clan in top:
        medal = "🥇" if clan["rank"] == 1 else "🥈" if clan["rank"] == 2 else "🥉" if clan["rank"] == 3 else f"{clan['rank']}."
        lines.append(
            f"{medal} <b>{clan['name']}</b> [{clan['tag']}] — "
            f"{format_kg(clan['total_kg'])} кг ({clan['member_count']} чел.)"
        )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 К информации о клане", callback_data="clan_info")
    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())