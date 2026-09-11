"""Main entry point for Potatobot."""

import asyncio
import signal
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import get_settings
from app.database import Database, init_database
from app.services import DigService, CleanupService
from app.handlers import basic_router, dig_router, stats_router
from app.middleware import RateLimitMiddleware, ErrorHandlingMiddleware, LoggingMiddleware
from app.web import create_web_app, run_web_server
from app.utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


async def main():
    settings = get_settings()
    
    # Setup logging
    setup_logging(settings.log_level, settings.log_format)
    logger.info("bot_starting", version="2.0.0")
    
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
    
    # Initialize bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.db = db  # Attach db for handlers
    
    dp = Dispatcher()
    
    # Register middlewares (order matters!)
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(ErrorHandlingMiddleware())
    
    # Register handlers
    dp.include_router(basic_router)
    dp.include_router(dig_router)
    dp.include_router(stats_router)
    
    # Set bot commands
    await bot.set_my_commands([
        ("start", "🏁 Начать / перезапустить"),
        ("dig", "🥔 Выкопать картошку"),
        ("my_stats", "📊 Моя статистика"),
        ("my_history", "📜 История копок"),
        ("top_day", "🏆 Топ за сутки"),
        ("top_all", "🏆 Общий топ"),
        ("help", "❓ Помощь"),
    ])
    
    # Start web server
    web_app = await create_web_app(db)
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
        await web_runner.cleanup()
        await bot.session.close()
        await db.close()
        logger.info("bot_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass