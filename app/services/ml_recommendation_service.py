"""ML Recommendations service for personalized suggestions."""

import json
import time
import random
from dataclasses import dataclass
from typing import Optional, List, Dict
from app.database import Database
from app.services import get_redis
from app.utils.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)


@dataclass
class UserProfile:
    user_id: int
    tg_id: int
    total_kg: float
    digs_count: int
    avg_kg_per_dig: float
    favorite_hour: Optional[int]
    favorite_day: Optional[int]
    streak: int
    clan_id: Optional[int]
    achievements_count: int
    last_active: float


@dataclass
class Recommendation:
    type: str  # "dig_time", "clan", "achievement", "strategy", "social"
    title: str
    description: str
    priority: int  # 1-10
    action_text: str
    action_data: Dict


class MLRecommendationService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._redis = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    async def get_user_profile(self, user_id: int) -> Optional[UserProfile]:
        """Build user profile from database."""
        async with self.db.acquire() as conn:
            # Basic stats
            user = await conn.fetchrow(
                "SELECT user_id, tg_id, total_kg, clan_id FROM users WHERE user_id = $1",
                user_id,
            )
            if not user:
                return None

            # Dig stats
            digs = await conn.fetch(
                "SELECT kg, timestamp FROM dig_history WHERE user_id = $1 ORDER BY timestamp",
                user_id,
            )

            if not digs:
                return UserProfile(
                    user_id=user["user_id"],
                    tg_id=user["tg_id"],
                    total_kg=0.0,
                    digs_count=0,
                    avg_kg_per_dig=0.0,
                    favorite_hour=None,
                    favorite_day=None,
                    streak=0,
                    clan_id=user["clan_id"],
                    achievements_count=0,
                    last_active=0,
                )

            # Calculate stats
            total_kg = sum(d["kg"] for d in digs)
            digs_count = len(digs)
            avg_kg = total_kg / digs_count

            # Favorite hour
            hours = [int(time.localtime(d["timestamp"]).tm_hour) for d in digs]
            favorite_hour = max(set(hours), key=hours.count) if hours else None

            # Favorite day (0=Monday)
            days = [time.localtime(d["timestamp"]).tm_wday for d in digs]
            favorite_day = max(set(days), key=days.count) if days else None

            # Last active
            last_active = digs[-1]["timestamp"]

            # Streak
            streak = await self._calculate_streak(user_id)

            # Achievements count
            redis = await self.redis
            achievements = await redis.get_user_achievements(user_id)

            return UserProfile(
                user_id=user["user_id"],
                tg_id=user["tg_id"],
                total_kg=user["total_kg"],
                digs_count=digs_count,
                avg_kg_per_dig=avg_kg,
                favorite_hour=favorite_hour,
                favorite_day=favorite_day,
                streak=streak,
                clan_id=user["clan_id"],
                achievements_count=len(achievements),
                last_active=last_active,
            )

    async def _calculate_streak(self, user_id: int) -> int:
        """Calculate current daily bonus streak."""
        redis = await self.redis
        streak, _ = await redis.get_daily_streak(user_id)
        return streak

    async def generate_recommendations(self, user_id: int) -> List[Recommendation]:
        """Generate personalized recommendations."""
        profile = await self.get_user_profile(user_id)
        if not profile:
            return []

        recommendations = []

        # 1. Optimal dig time recommendation
        if profile.favorite_hour is not None and profile.digs_count > 10:
            rec = await self._recommend_dig_time(profile)
            if rec:
                recommendations.append(rec)

        # 2. Clan recommendation
        if not profile.clan_id:
            rec = await self._recommend_clan(profile)
            if rec:
                recommendations.append(rec)

        # 3. Achievement hunting
        rec = await self._recommend_achievements(profile)
        if rec:
            recommendations.extend(rec)

        # 4. Strategy tips
        rec = await self._recommend_strategy(profile)
        if rec:
            recommendations.append(rec)

        # 5. Social recommendations
        rec = await self._recommend_social(profile)
        if rec:
            recommendations.append(rec)

        # Sort by priority
        recommendations.sort(key=lambda r: r.priority, reverse=True)

        # Cache for 1 hour
        redis = await self.redis
        cache_key = f"recommendations:{user_id}"
        await redis.set(cache_key, [r.__dict__ for r in recommendations[:5]], 3600)

        return recommendations[:5]

    async def _recommend_dig_time(self, profile: UserProfile) -> Optional[Recommendation]:
        """Recommend optimal dig time based on history."""
        if profile.favorite_hour is None:
            return None

        hour = profile.favorite_hour
        time_names = {
            0: "полночь", 1: "1 ночи", 2: "2 ночи", 3: "3 ночи",
            4: "4 утра", 5: "5 утра", 6: "6 утра", 7: "7 утра",
            8: "8 утра", 9: "9 утра", 10: "10 утра", 11: "11 утра",
            12: "полдень", 13: "13:00", 14: "14:00", 15: "15:00",
            16: "16:00", 17: "17:00", 18: "18:00", 19: "19:00",
            20: "20:00", 21: "21:00", 22: "22:00", 23: "23:00",
        }

        return Recommendation(
            type="dig_time",
            title="⏰ Оптимальное время для копания",
            description=f"Ты чаще всего копаешь в {time_names.get(hour, f'{hour}:00')}. "
                        f"Попробуй заходить в это время — картошка может быть крупнее!",
            priority=8,
            action_text="Поставить напоминание",
            action_data={"type": "set_reminder", "hour": hour},
        )

    async def _recommend_clan(self, profile: UserProfile) -> Optional[Recommendation]:
        """Recommend joining a clan."""
        if profile.clan_id:
            return None

        # Find active clans with similar players
        redis = await self.redis
        top_clans = await redis.get_leaderboard("clan", 5)

        if not top_clans:
            return Recommendation(
                type="clan",
                title="🏷 Создай свой клан!",
                description="Кланы дают бонусы за командную игру. Создай клан и зови друзей!",
                priority=7,
                action_text="Создать клан",
                action_data={"type": "create_clan"},
            )

        return Recommendation(
            type="clan",
            title="🏷 Присоединись к клану!",
            description=f"Топ клан \"{top_clans[0]['name']}\" [{top_clans[0]['tag']}] набирает {top_clans[0]['member_count']} участников. "
                        f"В кланах веселее и есть бонусы за командный вес!",
            priority=7,
            action_text="Посмотреть кланы",
            action_data={"type": "view_clans"},
        )

    async def _recommend_achievements(self, profile: UserProfile) -> List[Recommendation]:
        """Recommend next achievements to unlock."""
        recommendations = []

        # Weight-based achievements
        if profile.total_kg < 10:
            recommendations.append(Recommendation(
                type="achievement",
                title="🎯 Ближайшая цель: 10 кг",
                description=f"До достижения \"Десятка\" осталось {10 - profile.total_kg:.1f} кг. "
                            f"Осталось {int((10 - profile.total_kg) / max(profile.avg_kg_per_dig, 1))} копок!",
                priority=9,
                action_text="Копать",
                action_data={"type": "dig"},
            ))
        elif profile.total_kg < 100:
            recommendations.append(Recommendation(
                type="achievement",
                title="🎯 Цель: 100 кг (Центнер)",
                description=f"Прогресс: {profile.total_kg:.1f}/100 кг. "
                            f"Примерно {int((100 - profile.total_kg) / max(profile.avg_kg_per_dig, 1))} копок до достижения!",
                priority=8,
                action_text="Копать",
                action_data={"type": "dig"},
            ))

        # Streak achievements
        if profile.streak < 3:
            recommendations.append(Recommendation(
                type="achievement",
                title="🔥 Стрик: 3 дня",
                description=f"Твой текущий стрик: {profile.streak} дн. Заходи ежедневно за бонусом!",
                priority=8,
                action_text="Получить бонус",
                action_data={"type": "daily_bonus"},
            ))

        # Dig count achievements
        if profile.digs_count < 10:
            recommendations.append(Recommendation(
                type="achievement",
                title="⛏ Достижение: 10 копок",
                description=f"Сделано {profile.digs_count}/10 копок. Ещё немного!",
                priority=7,
                action_text="Копать",
                action_data={"type": "dig"},
            ))

        return recommendations

    async def _recommend_strategy(self, profile: UserProfile) -> Optional[Recommendation]:
        """Recommend digging strategy."""
        if profile.digs_count < 5:
            return Recommendation(
                type="strategy",
                title="💡 Совет новичка",
                description="Начинай с /dig каждый час. Не забывай забирать /daily бонус каждый день!",
                priority=6,
                action_text="Понял",
                action_data={"type": "acknowledge"},
            )

        if profile.avg_kg_per_dig < 3.5:
            return Recommendation(
                type="strategy",
                title="📊 Твой средний вес ниже среднего",
                description=f"Средний вес копа: {profile.avg_kg_per_dig:.1f} кг. "
                            f"Попробуй копать в разное время — может повезёт с крупной картошкой!",
                priority=5,
                action_text="Попробовать",
                action_data={"type": "dig"},
            )

        return None

    async def _recommend_social(self, profile: UserProfile) -> Optional[Recommendation]:
        """Recommend social features."""
        if profile.clan_id:
            return Recommendation(
                type="social",
                title="👥 Пригласи друга в клан!",
                description="Вместе копать веселее. Пригласи друга командой /clan_invite @username "
                            "и получайте бонусы за командный вес!",
                priority=5,
                action_text="Пригласить",
                action_data={"type": "invite_friend"},
            )

        return Recommendation(
            type="social",
            title="📱 Поделись достижением!",
            description=f"У тебя {profile.achievements_count} достижений. Поделись в чат — может, друзья захотят посоревноваться!",
            priority=4,
            action_text="Поделиться",
            action_data={"type": "share_achievement"},
        )

    async def get_cached_recommendations(self, user_id: int) -> List[Recommendation]:
        """Get cached recommendations or generate new."""
        redis = await self.redis
        cached = await redis.get(f"recommendations:{user_id}")
        if cached:
            return [Recommendation(**r) for r in cached]
        return await self.generate_recommendations(user_id)

    async def invalidate_cache(self, user_id: int):
        """Invalidate recommendations cache."""
        redis = await self.redis
        await redis.delete(f"recommendations:{user_id}")


# Global instance
_ml_service = None


def get_ml_service(db: Database = None) -> MLRecommendationService:
    global _ml_service
    if _ml_service is None and db is not None:
        _ml_service = MLRecommendationService(db)
    return _ml_service