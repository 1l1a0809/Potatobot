"""Achievement service."""

from dataclasses import dataclass
from app.config import get_settings
from app.services import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Achievement:
    id: str
    name: str
    description: str
    icon: str
    hidden: bool = False


# Achievement definitions
ACHIEVEMENTS = {
    # Dig achievements
    "first_dig": Achievement(
        id="first_dig",
        name="Первая картошка",
        description="Выкопай свою первую картошку",
        icon="🥔",
    ),
    "dig_10": Achievement(
        id="dig_10",
        name="Новичок",
        description="Соверши 10 копок",
        icon="⛏",
    ),
    "dig_100": Achievement(
        id="dig_100",
        name="Опытный фермер",
        description="Соверши 100 копок",
        icon="🚜",
    ),
    "dig_1000": Achievement(
        id="dig_1000",
        name="Мастер копания",
        description="Соверши 1000 копок",
        icon="💎",
    ),

    # Weight achievements
    "weight_10": Achievement(
        id="weight_10",
        name="Десятка",
        description="Накопи 10 кг картошки",
        icon="📦",
    ),
    "weight_100": Achievement(
        id="weight_100",
        name="Центнер",
        description="Накопи 100 кг картошки",
        icon="💯",
    ),
    "weight_1000": Achievement(
        id="weight_1000",
        name="Тонна",
        description="Накопи 1000 кг картошки",
        icon="🏋️",
    ),

    # Streak achievements
    "streak_3": Achievement(
        id="streak_3",
        name="Три дня",
        description="Заходи 3 дня подряд",
        icon="🔥",
    ),
    "streak_7": Achievement(
        id="streak_7",
        name="Неделя",
        description="Заходи 7 дней подряд",
        icon="📅",
    ),
    "streak_14": Achievement(
        id="streak_14",
        name="Две недели",
        description="Заходи 14 дней подряд",
        icon="🗓",
    ),
    "streak_30": Achievement(
        id="streak_30",
        name="Месяц",
        description="Заходи 30 дней подряд",
        icon="🏆",
    ),

    # Top achievements
    "top_day_1": Achievement(
        id="top_day_1",
        name="Король дня",
        description="Займи 1-е место в топе за сутки",
        icon="🥇",
    ),
    "top_day_3": Achievement(
        id="top_day_3",
        name="Призёр дня",
        description="Займи место в топ-3 за сутки",
        icon="🥈",
    ),
    "top_all_1": Achievement(
        id="top_all_1",
        name="Абсолютный чемпион",
        description="Займи 1-е место в общем топе",
        icon="👑",
    ),

    # Special
    "big_potato": Achievement(
        id="big_potato",
        name="Огромная картошка",
        description="Выкопай картошку весом 7.0 кг",
        icon="🎃",
    ),
    "night_owl": Achievement(
        id="night_owl",
        name="Сова",
        description="Копай между 00:00 и 06:00",
        icon="🦉",
    ),
    "early_bird": Achievement(
        id="early_bird",
        name="Жаворонок",
        description="Копай между 06:00 и 08:00",
        icon="🐦",
    ),
}


class AchievementService:
    def __init__(self):
        self.settings = get_settings()
        self._redis = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    def get_achievement(self, achievement_id: str) -> Achievement | None:
        return ACHIEVEMENTS.get(achievement_id)

    def get_all_achievements(self) -> list[Achievement]:
        return list(ACHIEVEMENTS.values())

    async def get_user_achievements(self, user_id: int) -> set[str]:
        redis = await self.redis
        return await redis.get_user_achievements(user_id)

    async def unlock(self, user_id: int, achievement_id: str) -> bool:
        if achievement_id not in ACHIEVEMENTS:
            return False

        redis = await self.redis
        unlocked = await redis.unlock_achievement(user_id, achievement_id)

        if unlocked:
            ach = ACHIEVEMENTS[achievement_id]
            logger.info("achievement_unlocked", user_id=user_id, achievement=achievement_id)
            return True
        return False

    async def check_and_unlock(self, user_id: int, context: dict) -> list[str]:
        """Check all achievements and unlock new ones based on context."""
        unlocked = []
        user_achievements = await self.get_user_achievements(user_id)

        for ach_id, ach in ACHIEVEMENTS.items():
            if ach_id in user_achievements:
                continue

            if await self._check_condition(ach_id, context):
                if await self.unlock(user_id, ach_id):
                    unlocked.append(ach_id)

        return unlocked

    async def _check_condition(self, achievement_id: str, context: dict) -> bool:
        """Check if achievement condition is met."""
        if achievement_id == "first_dig":
            return context.get("digs_count", 0) >= 1
        elif achievement_id == "dig_10":
            return context.get("digs_count", 0) >= 10
        elif achievement_id == "dig_100":
            return context.get("digs_count", 0) >= 100
        elif achievement_id == "dig_1000":
            return context.get("digs_count", 0) >= 1000
        elif achievement_id == "weight_10":
            return context.get("total_kg", 0) >= 10
        elif achievement_id == "weight_100":
            return context.get("total_kg", 0) >= 100
        elif achievement_id == "weight_1000":
            return context.get("total_kg", 0) >= 1000
        elif achievement_id == "streak_3":
            return context.get("streak", 0) >= 3
        elif achievement_id == "streak_7":
            return context.get("streak", 0) >= 7
        elif achievement_id == "streak_14":
            return context.get("streak", 0) >= 14
        elif achievement_id == "streak_30":
            return context.get("streak", 0) >= 30
        elif achievement_id == "big_potato":
            return context.get("last_kg", 0) >= 7.0
        elif achievement_id == "night_owl":
            hour = context.get("hour", 12)
            return 0 <= hour < 6
        elif achievement_id == "early_bird":
            hour = context.get("hour", 12)
            return 6 <= hour < 8
        return False


# Global instance
_achievement_service = None


def get_achievement_service() -> AchievementService:
    global _achievement_service
    if _achievement_service is None:
        _achievement_service = AchievementService()
    return _achievement_service