"""Chaos Engineering handlers for admin testing."""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.services import get_chaos_service, ChaosExperimentType
from app.config import get_settings
from app.utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def is_admin(user_id: int, settings) -> bool:
    return user_id in settings.admin_ids


@router.message(Command("chaos"))
async def chaos_handler(message: Message):
    """Chaos engineering dashboard."""
    settings = get_settings()
    if not is_admin(message.from_user.id, settings):
        await message.answer("❌ Доступ запрещен")
        return

    chaos_service = get_chaos_service(message.bot.db)
    experiments = chaos_service.list_experiments()

    lines = ["🧪 <b>Chaos Engineering</b>\n"]

    if not experiments:
        lines.append("Нет экспериментов. Создай новый ниже.")
    else:
        for exp in experiments:
            status_emoji = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "aborted": "⏹",
            }.get(exp.status.value, "❓")

            duration = ""
            if exp.duration_seconds:
                duration = f" ({exp.duration_seconds:.1f}s)"

            lines.append(
                f"{status_emoji} <b>{exp.name}</b> [{exp.type.value}]{duration}\n"
                f"   ID: <code>{exp.experiment_id}</code>\n"
                f"   Статус: {exp.status.value}\n"
            )

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать эксперимент", callback_data="chaos_create")
    kb.button(text="📋 Шаблоны", callback_data="chaos_templates")
    kb.button(text="🛑 Остановить все", callback_data="chaos_stop_all")
    kb.adjust(2, 1)

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())


@router.callback_query(F.data == "chaos_templates")
async def chaos_templates_callback(callback: CallbackQuery):
    chaos_service = get_chaos_service(callback.bot.db)
    templates = chaos_service.get_predefined_experiments()

    lines = ["📋 <b>Готовые шаблоны экспериментов</b>\n"]
    kb = InlineKeyboardBuilder()

    for i, template in enumerate(chaos_service.get_predefined_experiments()):
        lines.append(
            f"{i+1}. <b>{template['name']}</b> ({template['type']})\n"
            f"   {template['description']}\n"
        )
        kb.button(
            text=f"▶️ {template['name']}",
            callback_data=f"chaos_run_{template['type']}",
        )

    kb.button(text="🔙 Назад", callback_data="chaos_back")
    kb.adjust(1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("chaos_run_"))
async def chaos_run_template_callback(callback: CallbackQuery):
    exp_type_str = callback.data.replace("chaos_run_", "")
    try:
        exp_type = ChaosExperimentType(exp_type_str)
    except ValueError:
        await callback.answer("Неизвестный тип эксперимента", show_alert=True)
        return

    # Find template
    chaos_service = get_chaos_service(callback.bot.db)
    templates = chaos_service.get_predefined_experiments()
    template = next((t for t in chaos_service.get_predefined_experiments() if t["type"] == exp_type_str), None)

    if not template:
        await callback.answer("Шаблон не найден", show_alert=True)
        return

    chaos_service = get_chaos_service(callback.bot.db)
    experiment = chaos_service.create_experiment(
        name=template["name"],
        exp_type=exp_type,
        config=template["config"],
    )

    await callback.message.edit_text(
        f"🚀 <b>Запуск эксперимента</b>\n\n"
        f"<b>{experiment.name}</b>\n"
        f"ID: <code>{experiment.experiment_id}</code>\n"
        f"Тип: {experiment.type.value}\n"
        f"Конфиг: {experiment.config}\n\n"
        f"Запускаю...",
        parse_mode="HTML",
    )

    # Run experiment in background
    async def run_exp():
        try:
            result = await chaos_service.run_experiment(experiment.experiment_id)
            # Could send notification to admin
        except Exception as e:
            logger.error("chaos_experiment_error", experiment_id=experiment.experiment_id, error=str(e))

    import asyncio
    asyncio.create_task(run_exp())

    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 К списку", callback_data="chaos_back")
    await callback.message.edit_text(
        f"✅ Эксперимент <b>{experiment.name}</b> запущен!\n"
        f"ID: <code>{experiment.experiment_id}</code>\n\n"
        f"Результаты появятся в списке после завершения.",
        parse_mode="HTML",
        reply_markup=kb.as_markup(),
    )
    await callback.answer("Эксперимент запущен!")


@router.callback_query(F.data == "chaos_stop_all")
async def chaos_stop_all_callback(callback: CallbackQuery):
    chaos_service = get_chaos_service(callback.bot.db)
    experiments = chaos_service.list_experiments()

    stopped = 0
    for exp in chaos_service.list_experiments():
        if exp.status == "running":
            await chaos_service.abort_experiment(exp.experiment_id)
            stopped += 1

    await callback.answer(f"Остановлено {stopped} экспериментов")
    await callback.message.edit_text(f"🛑 Остановлено {stopped} запущенных экспериментов")


@router.callback_query(F.data == "chaos_back")
async def chaos_back_callback(callback: CallbackQuery):
    chaos_service = get_chaos_service(callback.bot.db)
    experiments = chaos_service.list_experiments()

    lines = ["🧪 <b>Chaos Engineering</b>\n"]

    if not experiments:
        lines.append("Нет экспериментов. Создай новый ниже.")
    else:
        for exp in experiments:
            status_emoji = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "aborted": "⏹",
            }.get(exp.status.value, "❓")

            duration = ""
            if exp.duration_seconds:
                duration = f" ({exp.duration_seconds:.1f}s)"

            lines.append(
                f"{status_emoji} <b>{exp.name}</b> [{exp.type.value}]{duration}\n"
                f"   ID: <code>{exp.experiment_id}</code>\n"
                f"   Статус: {exp.status.value}\n"
            )

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать эксперимент", callback_data="chaos_create")
    kb.button(text="📋 Шаблоны", callback_data="chaos_templates")
    kb.button(text="🛑 Остановить все", callback_data="chaos_stop_all")
    kb.adjust(2, 1)

    await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb.as_markup())
    await callback.answer()


# Custom experiment creation
@router.message(Command("chaos_create"))
async def chaos_create_handler(message: Message):
    settings = get_settings()
    if not is_admin(message.from_user.id, settings):
        return

    await message.answer(
        "🧪 <b>Создание кастомного эксперимента</b>\n\n"
        "Использование:\n"
        "<code>/chaos_create latency 2000 60</code> — задержка 2с на 60 сек\n"
        "<code>/chaos_create error 0.1 60</code> — 10% ошибок на 60 сек\n"
        "<code>/chaos_create db_failure 30</code> — падение БД на 30 сек\n"
        "<code>/chaos_create redis_failure 30</code> — падение Redis на 30 сек\n\n"
        "Типы: latency, error, db_failure, redis_failure, partial, resource, network",
        parse_mode="HTML",
    )


@router.message(Command("chaos_custom"))
async def chaos_custom_handler(message: Message):
    settings = get_settings()
    if not is_admin(message.from_user.id, settings):
        return

    args = message.text.split()
    if len(args) < 3:
        await message.answer(
            "❌ Использование: <code>/chaos_custom <тип> <параметры></code>\n\n"
            "Примеры:\n"
            "<code>/chaos_custom latency 2000 60</code>\n"
            "<code>/chaos_custom error 0.1 60</code>\n"
            "<code>/chaos_custom db_failure 30</code>\n"
            "<code>/chaos_custom partial 0.5 5000 60</code>",
            parse_mode="HTML",
        )
        return

    exp_type_str = args[1]
    try:
        if exp_type_str == "latency":
            latency_ms = int(args[2])
            duration = int(args[3]) if len(args) > 3 else 60
            config = {"latency_ms": latency_ms, "duration_seconds": duration}
            exp_type = ChaosExperimentType.LATENCY_INJECTION
            name = f"Custom Latency {args[2]}ms"
        elif exp_type_str == "error":
            error_rate = float(args[2])
            duration = int(args[3]) if len(args) > 3 else 60
            config = {"error_rate": error_rate, "duration_seconds": duration}
            exp_type = ChaosExperimentType.ERROR_INJECTION
            name = f"Custom Error {args[2]*100}%"
        elif exp_type_str == "db_failure":
            duration = int(args[2]) if len(args) > 2 else 30
            config = {"duration_seconds": duration}
            exp_type = ChaosExperimentType.DB_CONNECTION_FAILURE
            name = "Custom DB Failure"
        elif exp_type_str == "redis_failure":
            duration = int(args[2]) if len(args) > 2 else 30
            config = {"duration_seconds": duration}
            exp_type = ChaosExperimentType.REDIS_CONNECTION_FAILURE
            name = "Custom Redis Failure"
        elif exp_type_str == "partial":
            error_rate = float(args[2])
            latency_ms = int(args[3])
            duration = int(args[4]) if len(args) > 4 else 60
            config = {"error_rate": error_rate, "latency_ms": latency_ms, "duration_seconds": duration}
            exp_type = ChaosExperimentType.PARTIAL_OUTAGE
            name = f"Custom Partial {args[2]*100}%"
        elif exp_type_str == "resource":
            latency_ms = int(args[2])
            duration = int(args[3]) if len(args) > 3 else 120
            config = {"latency_ms": latency_ms, "duration_seconds": duration}
            exp_type = ChaosExperimentType.RESOURCE_EXHAUSTION
            name = f"Custom Resource {args[2]}ms"
        elif exp_type_str == "network":
            duration = int(args[2]) if len(args) > 2 else 30
            config = {"duration_seconds": duration}
            exp_type = ChaosExperimentType.NETWORK_PARTITION
            name = "Custom Network Partition"
        else:
            await message.answer("❌ Неизвестный тип")
            return
    except (ValueError, IndexError) as e:
        await message.answer(f"❌ Неверные параметры: {e}")
        return

    chaos_service = get_chaos_service(message.bot.db)
    experiment = chaos_service.create_experiment(name=name, exp_type=exp_type, config=config)

    # Run in background
    import asyncio
    asyncio.create_task(run_experiment_async(chaos_service, experiment))

    await message.answer(
        f"🚀 <b>Кастомный эксперимент запущен!</b>\n\n"
        f"<b>{name}</b>\n"
        f"ID: <code>{experiment.experiment_id}</code>\n"
        f"Тип: {exp_type.value}\n"
        f"Конфиг: {config}",
        parse_mode="HTML",
    )


async def run_experiment_async(chaos_service, experiment):
    try:
        await chaos_service.run_experiment(experiment.experiment_id)
    except Exception as e:
        logger.error("chaos_experiment_error", experiment_id=experiment.experiment_id, error=str(e))