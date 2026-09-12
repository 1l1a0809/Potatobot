"""Main entry point for Potatobot."""

import asyncio
import signal
import sys
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings
from app.database import Database, init_database
from app.services import (
    DigService,
    CleanupService,
    get_redis,
    close_redis,
    get_daily_bonus_service,
    get_achievement_service,
    get_metrics_service,
    get_clan_service,
    get_ml_service,
)
from app.handlers import basic_router, dig_router, stats_router, webapp_router, inline_router, clan_router, ml_recommendations_router, chaos_router
from app.middleware import RateLimitMiddleware, ErrorHandlingMiddleware, LoggingMiddleware
from app.web import create_web_app, run_web_server
from app.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


def init_sentry(settings) -> None:
    """Initialize Sentry SDK."""
    if not settings.sentry_dsn:
        logger.info("sentry_disabled")
        return

    sentry_logging = LoggingIntegration(
        level=None,  # Capture all levels
        event_level=None,  # Send all events
    )

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        integrations=[
            AsyncioIntegration(),
            sentry_logging,
        ],
        environment="production",
        release="potatobot@2.1.0",
    )
    logger.info("sentry_initialized")


async def main():
    settings = get_settings()

    # Setup logging
    setup_logging(settings.log_level, settings.log_format)
    logger.info("bot_starting", version="2.1.0")

    # Initialize Sentry
    init_sentry(settings)

    # Initialize Redis
    redis = await get_redis()
    logger.info("redis_connected")

    # Initialize database
    db = Database(
        settings.database_url,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    await db.connect()
    await init_database(settings.database_url)
    logger.info("database_connected")

    # Initialize services
    dig_service = DigService(db)
    cleanup_service = CleanupService(db)
    await cleanup_service.start()

    metrics_service = get_metrics_service(db)
    await metrics_service.start()

clan_service = get_clan_service(db)

    ml_service = get_ml_service(db)

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = db  # Inject db

    achievement_service = get_achievement_service()

    # Initialize bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.db = db
    bot.dig_service = dig_service
    bot.daily_bonus_service = daily_bonus_service
    bot.achievement_service = achievement_service
    bot.clan_service = clan_service
    bot.ml_service = ml_service
    bot.settings = settings
    bot.admin_ids = settings.admin_ids

    dp = Dispatcher()

    # Register middlewares (order matters!)

    # Register handlers
    dp.include_router(basic_router)
    dp.include_router(dig_router)
    dp.include_router(stats_router)
    dp.include_router(webapp_router)
    dp.include_router(inline_router)
    dp.include_router(clan_router)
    dp.include_router(ml_recommendations_router)
    dp.include_router(chaos_router)

    # Set bot commands
    await bot.set_my_commands([
        ("start", "🏁 Начать / перезапустить"),
        ("dig", "🥔 Выкопать картошку"),
        ("my_stats", "📊 Моя статистика"),
        ("my_history", "📜 История копок"),
        ("top_day", "🏆 Топ за сутки"),
        ("top_all", "🏆 Общий топ"),
        ("daily", "🎁 Ежедневный бонус"),
        ("achievements", "🏅 Достижения"),
        ("app", "🌐 Веб-приложение"),
        ("clan", "🏷 Мой клан"),
        ("clan_create", "🏷 Создать клан"),
        ("clan_invite", "📨 Пригласить в клан"),
        ("clan_invites", "📨 Входящие приглашения"),
        ("clan_top", "🏆 Топ кланов"),
        ("clan_transfer", "👑 Передать владение кланом"),
        ("help", "❓ Помощь"),
    ])

    # Start web server
    web_app = await create_web_app(db, redis, settings, bot)
    web_runner = await run_web_server(web_app, settings.web_host, settings.web_port)
    logger.info("web_server_started", host=settings.web_host, port=settings.web_port)

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("shutdown_signal_received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    # Start polling
    logger.info("bot_polling_started")
    polling_task = asyncio.create_task(dp.start_polling(bot))

    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("bot_shutting_down")
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

        await cleanup_service.stop()
        await metrics_service.stop()
        await web_runner.cleanup()
        await bot.session.close()
        await db.close()
        await close_redis()
        logger.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass