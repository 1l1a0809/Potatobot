"""Redis service for caching, rate limiting, and sessions."""

import json
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RedisService:
    def __init__(self):
        self.settings = get_settings()
        self._pool: ConnectionPool | None = None
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        self._pool = ConnectionPool.from_url(
            self.settings.redis_url,
            max_connections=self.settings.redis_max_connections,
            decode_responses=True,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        # Test connection
        await self._client.ping()
        logger.info("redis_connected", url=self.settings.redis_url)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("redis_disconnected")

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis not connected")
        return self._client

    # ===== Generic Cache =====
    async def get(self, key: str) -> Any | None:
        value = await self.client.get(key)
        if value is not None:
            return json.loads(value)
        return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        await self.client.setex(key, ttl, json.dumps(value))

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return await self.client.exists(key) > 0

    async def increment(self, key: str, ttl: int) -> int:
        pipe = self.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return results[0]

    # ===== Rate Limiting =====
    async def check_rate_limit(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        """
        Check rate limit using sliding window.
        Returns (allowed, remaining)
        """
        now = time.time()
        pipeline = self.client.pipeline()
        pipeline.zremrangebyscore(key, 0, now - window)
        pipeline.zcard(key)
        pipeline.zadd(key, {str(now): now})
        pipeline.expire(key, window)
        results = await pipeline.execute()
        current_count = results[1]
        if current_count >= limit:
            return False, 0
        return True, limit - current_count - 1

    # ===== Leaderboard Cache =====
    async def get_leaderboard(self, period: str, limit: int) -> list[dict] | None:
        key = f"leaderboard:{period}:{limit}"
        return await self.get(key)

    async def set_leaderboard(self, period: str, limit: int, data: list[dict], ttl: int) -> None:
        key = f"leaderboard:{period}:{limit}"
        await self.set(key, data, ttl)

    async def invalidate_leaderboard(self, period: str | None = None, limit: int | None = None) -> None:
        if period and limit:
            await self.delete(f"leaderboard:{period}:{limit}")
        else:
            keys = await self.client.keys("leaderboard:*")
            if keys:
                await self.client.delete(*keys)

    # ===== Daily Bonus =====
    async def get_daily_streak(self, user_id: int) -> tuple[int, float]:
        """Returns (streak_days, last_claim_timestamp)"""
        key = f"daily_bonus:{user_id}"
        data = await self.client.hmget(key, "streak", "last_claim")
        streak = int(data[0]) if data[0] else 0
        last_claim = float(data[1]) if data[1] else 0
        return streak, last_claim

    async def claim_daily_bonus(self, user_id: int) -> tuple[float, int]:
        """
        Claim daily bonus.
        Returns (bonus_kg, new_streak)
        """
        settings = get_settings()
        key = f"daily_bonus:{user_id}"
        now = time.time()
        today_start = now - (now % 86400)

        streak, last_claim = await self.get_daily_streak(user_id)

        # Check if already claimed today
        if last_claim >= today_start:
            return 0.0, streak

        # Check if streak continues (claimed yesterday)
        yesterday_start = today_start - 86400
        if last_claim >= yesterday_start:
            streak = min(streak + 1, settings.daily_bonus_max_streak)
        else:
            streak = 1

        # Calculate bonus
        bonus = settings.daily_bonus_base_kg + (streak - 1) * settings.daily_bonus_streak_multiplier
        bonus = round(bonus, settings.dig_precision)

        # Save
        await self.client.hset(key, mapping={
            "streak": streak,
            "last_claim": now,
        })
        await self.client.expire(key, 86400 * 2)  # Keep for 2 days

        return bonus, streak

    # ===== Achievements =====
    async def get_user_achievements(self, user_id: int) -> set[str]:
        key = f"achievements:{user_id}"
        data = await self.client.smembers(key)
        return set(data) if data else set()

    async def unlock_achievement(self, user_id: int, achievement_id: str) -> bool:
        key = f"achievements:{user_id}"
        result = await self.client.sadd(key, achievement_id)
        return result > 0

    # ===== Anti-cheat =====
    async def record_dig(self, user_id: int, kg: float, timestamp: float) -> None:
        key = f"anticheat:digs:{user_id}"
        await self.client.zadd(key, {f"{timestamp}:{kg}": timestamp})
        await self.client.expire(key, 3600)  # Keep 1 hour

    async def get_recent_digs(self, user_id: int, limit: int = 50) -> list[tuple[float, float]]:
        key = f"anticheat:digs:{user_id}"
        results = await self.client.zrange(key, -limit, -1, withscores=True)
        return [(float(score), float(member.split(":")[1])) for member, score in results]

    async def get_digs_last_hour(self, user_id: int) -> list[tuple[float, float]]:
        key = f"anticheat:digs:{user_id}"
        now = time.time()
        results = await self.client.zrangebyscore(key, now - 3600, now, withscores=True)
        return [(float(score), float(member.split(":")[1])) for member, score in results]

    # ===== Sessions (for admin panel) =====
    async def create_session(self, session_id: str, user_id: int, ttl: int = 86400) -> None:
        key = f"session:{session_id}"
        await self.client.setex(key, ttl, str(user_id))

    async def get_session(self, session_id: str) -> int | None:
        key = f"session:{session_id}"
        value = await self.client.get(key)
        return int(value) if value else None

    async def delete_session(self, session_id: str) -> None:
        key = f"session:{session_id}"
        await self.client.delete(key)

    # ===== Metrics / Stats =====
    async def increment_counter(self, name: str, labels: dict[str, str] = None, value: int = 1) -> None:
        key = f"metrics:{name}"
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            key += f"{{{label_str}}}"
        await self.client.incrby(key, value)

    async def get_counter(self, name: str, labels: dict[str, str] = None) -> int:
        key = f"metrics:{name}"
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            key += f"{{{label_str}}}"
        value = await self.client.get(key)
        return int(value) if value else 0


# Global instance
_redis_service: RedisService | None = None


async def get_redis() -> RedisService:
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
        await _redis_service.connect()
    return _redis_service


async def close_redis() -> None:
    global _redis_service
    if _redis_service:
        await _redis_service.close()
        _redis_service = None