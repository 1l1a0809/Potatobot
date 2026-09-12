"""Daily bonus service."""

import time
from app.config import get_settings
from app.services import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)


class DailyBonusService:
    def __init__(self):
        self.settings = get_settings()
        self._redis = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def claim(self, tg_id: int) -> dict:
        """Claim daily bonus."""
        if not self.settings.daily_bonus_enabled:
            return {"success": False, "error": "Daily bonus disabled"}

        user = await self._get_user(tg_id)
        if not user:
            return {"success": False, "error": "User not found"}

        redis = await self.redis
        bonus_kg, streak = await redis.claim_daily_bonus(user.user_id)

        if bonus_kg == 0:
            return {"success": False, "error": "Already claimed today", "streak": streak}

        # Add to user's total
        await self._add_kg(user.user_id, bonus_kg)

        # Check achievements
        await self._check_streak_achievements(user.user_id, streak)

        logger.info("daily_bonus_claimed", user_id=user.user_id, bonus_kg=bonus_kg, streak=streak)

        return {
            "success": True,
            "bonus_kg": bonus_kg,
            "streak": streak,
            "message": self._format_message(bonus_kg, streak),
        }

    async def get_status(self, tg_id: int) -> dict:
        """Get daily bonus status."""
        user = await self._get_user(tg_id)
        if not user:
            return {"streak": 0, "can_claim": False}

        redis = await self.redis
        streak, last_claim = await redis.get_daily_streak(user.user_id)

        now = time.time()
        today_start = now - (now % 86400)
        can_claim = last_claim < today_start

        next_claim = today_start + 86400 if not can_claim else today_start
        remaining = int(next_claim - now)

        return {
            "streak": streak,
            "can_claim": can_claim,
            "remaining_seconds": remaining,
            "last_claim": last_claim if last_claim > 0 else None,
        }

    async def _get_user(self, tg_id: int):
        from app.database import Database
        db: Database = self.db if hasattr(self, 'db') else None
        # We'll inject db from main
        return None

    async def _add_kg(self, user_id: int, kg: float):
        from app.database import Database
        # Will be injected
        pass

    async def _check_streak_achievements(self, user_id: int, streak: int):
        achievements = {
            3: "streak_3",
            7: "streak_7",
            14: "streak_14",
            30: "streak_30",
        }
        for days, ach_id in achievements.items():
            if streak >= days:
                await self._unlock_achievement(user_id, ach_id)

    async def _unlock_achievement(self, user_id: int, achievement_id: str):
        redis = await self.redis
        unlocked = await redis.unlock_achievement(user_id, achievement_id)
        if unlocked:
            logger.info("achievement_unlocked", user_id=user_id, achievement=achievement_id)

    def _format_message(self, bonus_kg: float, streak: int) -> str:
        from app.utils.formatting import format_kg, format_duration
        streak_bonus = (streak - 1) * self.settings.daily_bonus_streak_multiplier
        return (
            f"🎁 <b>Ежедневный бонус получен!</b>\n\n"
            f"🥔 Получено: <b>{format_kg(bonus_kg)} кг</b>\n"
            f"🔥 Стрик: <b>{streak} дн.</b> (+{format_kg(streak_bonus)} кг)\n\n"
            f"Приходи завтра за большим бонусом!"
        )


# Global instance for injection
_daily_bonus_service = None


def get_daily_bonus_service() -> DailyBonusService:
    global _daily_bonus_service
    if _daily_bonus_service is None:
        _daily_bonus_service = DailyBonusService()
    return _daily_bonus_service