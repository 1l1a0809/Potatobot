"""Dig service for business logic."""

import random
import time
from app.database import Database
from app.exceptions import CooldownError
from app.config import get_settings
from app.utils.logging import get_logger
from app.utils.validators import validate_dig_amount
from app.services import get_redis, get_clan_service

logger = get_logger(__name__)


class DigService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._redis = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def perform_dig(self, tg_id: int, username: str | None) -> dict:
        """Perform a dig action."""
        user = await self.db.get_or_create_user(tg_id, username)

        # Check cooldown
        if user.last_dig_time:
            elapsed = time.time() - user.last_dig_time
            if elapsed < self.settings.dig_cooldown_seconds:
                remaining = int(self.settings.dig_cooldown_seconds - elapsed)
                logger.warning("dig_cooldown", user_id=user.user_id, remaining=remaining)
                raise CooldownError(remaining)

        # Anti-cheat checks
        if self.settings.anticheat_enabled:
            await self._anticheat_check(user.user_id)

        # Generate random kg
        kg = validate_dig_amount(
            random.uniform(self.settings.dig_min_kg, self.settings.dig_max_kg)
        )
        timestamp = time.time()

        # Save dig record
        dig_id = await self.db.add_dig_record(user.user_id, kg, timestamp)

        # Update user stats
        updated_user = await self.db.update_user_dig(user.user_id, kg, timestamp)

        # Record for anti-cheat
        if self.settings.anticheat_enabled:
            redis = await self.redis
            await redis.record_dig(user.user_id, kg, timestamp)

        # Invalidate leaderboard cache
        await self.invalidate_leaderboard_cache()

        # Increment metrics
        redis = await self.redis
        await redis.increment_counter("digs_total", {"status": "success"})
        await redis.increment_counter("dig_kg_total", value=int(kg * 10))  # Store as int * 10

        logger.info("dig_performed", user_id=user.user_id, kg=kg, dig_id=dig_id)

        # Add clan contribution
        clan_service = get_clan_service(self.db)
        await clan_service.add_contribution(user.user_id, kg)

        # Get digs count for achievements
        async with self.db.acquire() as conn:
            digs_count = await conn.fetchval(
                "SELECT COUNT(*) FROM dig_history WHERE user_id = $1",
                user.user_id,
            )

        return {
            "kg": kg,
            "total_kg": updated_user.total_kg,
            "remaining_cooldown": self.settings.dig_cooldown_seconds,
            "dig_id": dig_id,
            "digs_count": digs_count,
        }

    async def _anticheat_check(self, user_id: int) -> None:
        """Run anti-cheat checks."""
        redis = await self.redis

        # Check min interval between digs
        recent = await redis.get_recent_digs(user_id, 2)
        if len(recent) >= 2:
            last_ts, _ = recent[-1]
            prev_ts, _ = recent[-2]
            if last_ts - prev_ts < self.settings.anticheat_min_dig_interval:
                logger.warning("anticheat_min_interval", user_id=user_id, interval=last_ts - prev_ts)
                raise CooldownError(int(self.settings.dig_cooldown_seconds))

        # Check max kg per hour
        hour_digs = await redis.get_digs_last_hour(user_id)
        total_kg_hour = sum(kg for _, kg in hour_digs)
        if total_kg_hour > self.settings.anticheat_max_kg_per_hour:
            logger.warning("anticheat_max_kg_hour", user_id=user_id, total_kg=total_kg_hour)
            raise CooldownError(int(self.settings.dig_cooldown_seconds))

    async def get_user_history(self, tg_id: int, limit: int = 10) -> list:
        user = await self.db.get_user_by_tg_id(tg_id)
        if user is None:
            return []
        return await self.db.get_user_history(user.user_id, limit)

    async def get_top_day(self, limit: int = 10) -> list:
        redis = await self.redis
        cached = await redis.get_leaderboard("day", limit)
        if cached is not None:
            await redis.increment_counter("cache_hits", {"cache": "leaderboard_day"})
            return cached

        await redis.increment_counter("cache_misses", {"cache": "leaderboard_day"})
        result = await self.db.get_top_day(limit)
        await redis.set_leaderboard("day", limit, result, self.settings.leaderboard_cache_ttl)
        return result

    async def get_top_all(self, limit: int = 10) -> list:
        redis = await self.redis
        cached = await redis.get_leaderboard("all", limit)
        if cached is not None:
            await redis.increment_counter("cache_hits", {"cache": "leaderboard_all"})
            return cached

        await redis.increment_counter("cache_misses", {"cache": "leaderboard_all"})
        result = await self.db.get_top_all(limit)
        await redis.set_leaderboard("all", limit, result, self.settings.leaderboard_cache_ttl)
        return result

    async def invalidate_leaderboard_cache(self) -> None:
        redis = await self.redis
        await redis.invalidate_leaderboard()