"""Metrics service for DAU/WAU/Retention and other analytics."""

import asyncio
import time
from app.database import Database
from app.services import get_redis
from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class MetricsService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._redis = None
        self._task: asyncio.Task | None = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run_metrics_collection())
        logger.info("metrics_service_started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("metrics_service_stopped")

    async def _run_metrics_collection(self) -> None:
        # Initial collection
        await self.collect_all_metrics()

        while True:
            try:
                # Run every 5 minutes
                await asyncio.sleep(300)
                await self.collect_all_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("metrics_collection_failed", error=str(e), exc_info=True)

    async def collect_all_metrics(self) -> None:
        """Collect and update all metrics."""
        try:
            await self.update_active_users_metrics()
            await self.update_retention_metrics()
            logger.debug("metrics_collected")
        except Exception as e:
            logger.error("collect_all_metrics_failed", error=str(e), exc_info=True)

    async def update_active_users_metrics(self) -> None:
        """Update DAU, WAU, MAU metrics."""
        redis = await self.redis
        now = time.time()

        async with self.db.acquire() as conn:
            # DAU - active in last 24h
            dau = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM dig_history
                WHERE timestamp > $1
                """,
                now - 86400,
            )

            # WAU - active in last 7 days
            wau = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM dig_history
                WHERE timestamp > $1
                """,
                now - 604800,
            )

            # MAU - active in last 30 days
            mau = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM dig_history
                WHERE timestamp > $1
                """,
                now - 2592000,
            )

        await redis.client.set("metrics:dau", dau)
        await redis.client.set("metrics:wau", wau)
        await redis.client.set("metrics:mau", mau)

        # Also update Prometheus gauges via redis counters
        await redis.increment_counter("active_users_daily", value=dau)
        await redis.increment_counter("active_users_weekly", value=wau)
        await redis.increment_counter("active_users_monthly", value=mau)

    async def update_retention_metrics(self) -> None:
        """Calculate and update retention metrics (D1, D7, D30)."""
        redis = await self.redis
        now = time.time()

        async with self.db.acquire() as conn:
            # Day 1 retention: users who registered yesterday and dug today
            yesterday_start = now - (now % 86400) - 86400
            yesterday_end = yesterday_start + 86400
            today_start = now - (now % 86400)

            # Users registered yesterday
            reg_yesterday = await conn.fetch(
                """
                SELECT user_id FROM users
                WHERE created_at >= $1 AND created_at < $2
                """,
                yesterday_start, yesterday_end,
            )
            reg_yesterday_ids = [r["user_id"] for r in reg_yesterday]

            if reg_yesterday_ids:
                placeholders = ",".join(f"${i+1}" for i in range(len(reg_yesterday_ids)))
                ret_d1 = await conn.fetchval(
                    f"""
                    SELECT COUNT(DISTINCT user_id)
                    FROM dig_history
                    WHERE user_id IN ({placeholders})
                    AND timestamp >= $1
                    """,
                    *reg_yesterday_ids, today_start,
                )
                retention_d1 = round(ret_d1 / len(reg_yesterday_ids) * 100, 1) if reg_yesterday_ids else 0
            else:
                retention_d1 = 0

            # Day 7 retention
            week_ago_start = now - (now % 86400) - 7 * 86400
            week_ago_end = week_ago_start + 86400
            week_ago_target = week_ago_start + 7 * 86400

            reg_week_ago = await conn.fetch(
                """
                SELECT user_id FROM users
                WHERE created_at >= $1 AND created_at < $2
                """,
                week_ago_start, week_ago_end,
            )
            reg_week_ago_ids = [r["user_id"] for r in reg_week_ago]

            if reg_week_ago_ids:
                placeholders = ",".join(f"${i+1}" for i in range(len(reg_week_ago_ids)))
                ret_d7 = await conn.fetchval(
                    f"""
                    SELECT COUNT(DISTINCT user_id)
                    FROM dig_history
                    WHERE user_id IN ({placeholders})
                    AND timestamp >= $1 AND timestamp < $2
                    """,
                    *reg_week_ago_ids, week_ago_target, week_ago_target + 86400,
                )
                retention_d7 = round(ret_d7 / len(reg_week_ago_ids) * 100, 1) if reg_week_ago_ids else 0
            else:
                retention_d7 = 0

            # Day 30 retention
            month_ago_start = now - (now % 86400) - 30 * 86400
            month_ago_end = month_ago_start + 86400
            month_ago_target = month_ago_start + 30 * 86400

            reg_month_ago = await conn.fetch(
                """
                SELECT user_id FROM users
                WHERE created_at >= $1 AND created_at < $2
                """,
                month_ago_start, month_ago_end,
            )
            reg_month_ago_ids = [r["user_id"] for r in reg_month_ago]

            if reg_month_ago_ids:
                placeholders = ",".join(f"${i+1}" for i in range(len(reg_month_ago_ids)))
                ret_d30 = await conn.fetchval(
                    f"""
                    SELECT COUNT(DISTINCT user_id)
                    FROM dig_history
                    WHERE user_id IN ({placeholders})
                    AND timestamp >= $1 AND timestamp < $2
                    """,
                    *reg_month_ago_ids, month_ago_target, month_ago_target + 86400,
                )
                retention_d30 = round(ret_d30 / len(reg_month_ago_ids) * 100, 1) if reg_month_ago_ids else 0
            else:
                retention_d30 = 0

        await redis.client.set("metrics:retention_d1", retention_d1)
        await redis.client.set("metrics:retention_d7", retention_d7)
        await redis.client.set("metrics:retention_d30", retention_d30)


# Global instance
_metrics_service = None


def get_metrics_service(db: Database = None) -> MetricsService:
    global _metrics_service
    if _metrics_service is None and db is not None:
        _metrics_service = MetricsService(db)
    return _metrics_service