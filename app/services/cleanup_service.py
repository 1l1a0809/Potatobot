"""Cleanup service for maintenance tasks."""

import asyncio
from app.database import Database
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class CleanupService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_cleanup())
        logger.info("cleanup_service_started", interval=self.settings.cleanup_interval_seconds)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("cleanup_service_stopped")

    async def _run_cleanup(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.settings.cleanup_interval_seconds)
                deleted = await self.db.cleanup_old_history(
                    self.settings.history_retention_hours * 3600
                )
                if deleted > 0:
                    logger.info("cleanup_completed", deleted_records=deleted)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("cleanup_failed", error=str(e), exc_info=True)