"""Dig service for business logic."""

import random
import time
from app.database import Database
from app.exceptions import CooldownError
from app.config import get_settings
from app.utils.logging import get_logger
from app.utils.validators import validate_dig_amount
from app.utils.cache import cached

logger = get_logger(__name__)


class DigService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()

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

        # Generate random kg
        kg = validate_dig_amount(
            random.uniform(self.settings.dig_min_kg, self.settings.dig_max_kg)
        )
        timestamp = time.time()

        # Save dig record
        dig_id = await self.db.add_dig_record(user.user_id, kg, timestamp)

        # Update user stats
        updated_user = await self.db.update_user_dig(user.user_id, kg, timestamp)

        logger.info("dig_performed", user_id=user.user_id, kg=kg, dig_id=dig_id)

        return {
            "kg": kg,
            "total_kg": updated_user.total_kg,
            "remaining_cooldown": self.settings.dig_cooldown_seconds,
            "dig_id": dig_id,
        }

    async def get_user_history(self, tg_id: int, limit: int = 10) -> list:
        user = await self.db.get_user_by_tg_id(tg_id)
        if user is None:
            return []
        return await self.db.get_user_history(user.user_id, limit)

    @cached(ttl=30, key_prefix="leaderboard")
    async def get_top_day(self, limit: int = 10):
        return await self.db.get_top_day(limit)

    @cached(ttl=30, key_prefix="leaderboard")
    async def get_top_all(self, limit: int = 10):
        return await self.db.get_top_all(limit)

    async def invalidate_leaderboard_cache(self):
        self.get_top_day.cache.clear()
        self.get_top_all.cache.clear()