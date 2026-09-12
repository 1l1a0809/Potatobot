"""Basic command handlers with onboarding."""

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from app.utils.logging import get_logger
from app.services import get_daily_bonus_service

router = Router()
logger = get_logger(__name__)


WELCOME_STEPS = [
    (
        "🥔 <b>Добро пожаловать в Potatobot!</b>",
        "Здесь ты копаешь картошку, соревнуешься с другими и получаешь достижения."
    ),
    (
        "⛏ <b>Как копать?</b>",
        "Нажми /dig — получишь случайную картошку от 1 до 7 кг.\n"
        "Копать можно раз в час. Картошка накапливается в твоём общем весе."
    ),
    (
        "🎁 <b>Ежедневный бонус</b>",
        "Каждый день заходи и получай бонус картошки командой /daily!\n"
        "Чем дольше твой стрик (дни подряд), тем больше бонус."
    ),
    (
        "🏅 <b>Достижения</b>",
        "Получай достижения за вес, стрики, попадание в топ и особенные моменты.\n"
        "Посмотреть все: /achievements"
    ),
    (
        "🏆 <b>Рейтинги</b>",
        "/top_day — топ за сутки\n"
        "/top_all — общий топ\n"
        "Соревнуйся с друзьями!"
    ),
    (
        "📊 <b>Твоя статистика</b>",
        "/my_stats — твой вес, стрик, бонус\n"
        "/my_history — история последних 10 копок"
    ),
]


@router.message(Command("start"))
async def start_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("step_"):
        # Onboarding step
        try:
            step = int(args[1].split("_")[1])
            await show_onboarding_step(message, step)
        except (ValueError, IndexError):
            await show_onboarding_step(message, 0)
    else:
        # First time - show welcome
        await show_onboarding_step(message, 0)


async def show_onboarding_step(message: Message, step: int):
    if step >= len(WELCOME_STEPS):
        # Onboarding complete
        await message.answer(
            "✅ <b>Обучение завершено!</b>\n\n"
            "Теперь ты знаешь всё. Начни с первой копки: /dig\n\n"
            "Удачи, фермер! 🥔",
            parse_mode="HTML",
        )
        return

    title, text = WELCOME_STEPS[step]
    next_step = step + 1

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    kb = InlineKeyboardBuilder()
    kb.button(text="Далее →", callback_data=f"onboard_{next_step}")

    await message.answer(
        f"{title}\n\n{text}\n\n"
        f"<i>Шаг {step + 1} из {len(WELCOME_STEPS)}</i>",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("onboard_"))
async def onboarding_callback(callback):
    try:
        step = int(callback.data.split("_")[1])
        await show_onboarding_step(callback.message, step)
        await callback.answer()
    except (ValueError, IndexError):
        await callback.answer("Ошибка")


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "🥔 <b>Potatobot — справка</b>\n\n"
        "<b>Как играть:</b>\n"
        "1. Нажми /dig — получишь случайную картошку (1-7 кг)\n"
        "2. Копать можно раз в час\n"
        "3. Картошка накапливается в твоем общем весе\n"
        "4. Сравнивайся с другими в /top_day и /top_all\n"
        "5. Забирай ежедневный бонус /daily\n"
        "6. Собирай достижения /achievements\n\n"
        "<b>Команды:</b>\n"
        "🥔 /dig — выкопать картошку (раз в час)\n"
        "🎁 /daily — ежедневный бонус\n"
        "🏅 /achievements — твои достижения\n"
        "📊 /my_stats — твоя статистика\n"
        "📜 /my_history — последние 10 копок\n"
        "🏆 /top_day — топ-10 за сутки\n"
        "🏆 /top_all — общий топ-10\n"
        "❓ /help — эта справка\n\n"
        "<b>Ссылка для друга:</b>\n"
        f"https://t.me/{(await message.bot.get_me()).username}?start=step_0",
        parse_mode="HTML",
    )