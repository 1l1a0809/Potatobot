"""Database connection and models."""

from __future__ import annotations

import asyncpg
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Optional
from app.config import get_settings
from sqlalchemy import BigInteger, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_dig_time: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class DigHistoryModel(Base):
    __tablename__ = "dig_history"

    dig_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    kg: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)


Index("idx_dig_history_user_timestamp", DigHistoryModel.user_id, DigHistoryModel.timestamp.desc())
Index("idx_dig_history_timestamp", DigHistoryModel.timestamp)


@dataclass
class User:
    user_id: int
    tg_id: int
    username: Optional[str]
    total_kg: float
    last_dig_time: Optional[float]
    created_at: float


@dataclass
class DigRecord:
    dig_id: int
    user_id: int
    kg: float
    timestamp: float


@dataclass
class LeaderboardEntry:
    rank: int
    username: str
    total_kg: float
    digs_count: int


class Database:
    def __init__(
        self,
        dsn: str,
        min_size: int = 10,
        max_size: int = 20,
    ):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
            command_timeout=30,
            server_settings={
                "application_name": "potatobot",
                "timezone": "UTC",
            },
        )

    @asynccontextmanager
    async def acquire(self):
        if self._pool is None:
            raise RuntimeError("Database not connected")
        async with self._pool.acquire() as conn:
            yield conn

    async def health_check(self) -> bool:
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    # User queries
    async def get_or_create_user(self, tg_id: int, username: Optional[str]) -> User:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (tg_id, username, total_kg, last_dig_time)
                VALUES ($1, $2, 0.0, NULL)
                ON CONFLICT (tg_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING user_id, tg_id, username, total_kg, last_dig_time, created_at
                """,
                tg_id,
                username,
            )
            return User(
                user_id=row["user_id"],
                tg_id=row["tg_id"],
                username=row["username"],
                total_kg=row["total_kg"],
                last_dig_time=row["last_dig_time"],
                created_at=row["created_at"],
            )

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[User]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_id, tg_id, username, total_kg, last_dig_time, created_at FROM users WHERE tg_id = $1",
                tg_id,
            )
            if row:
                return User(
                    user_id=row["user_id"],
                    tg_id=row["tg_id"],
                    username=row["username"],
                    total_kg=row["total_kg"],
                    last_dig_time=row["last_dig_time"],
                    created_at=row["created_at"],
                )
            return None

    async def update_user_dig(self, user_id: int, kg: float, timestamp: float) -> User:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE users
                SET total_kg = total_kg + $2,
                    last_dig_time = $3
                WHERE user_id = $1
                RETURNING user_id, tg_id, username, total_kg, last_dig_time, created_at
                """,
                user_id,
                kg,
                timestamp,
            )
            return User(
                user_id=row["user_id"],
                tg_id=row["tg_id"],
                username=row["username"],
                total_kg=row["total_kg"],
                last_dig_time=row["last_dig_time"],
                created_at=row["created_at"],
            )

    # Dig history queries
    async def add_dig_record(self, user_id: int, kg: float, timestamp: float) -> int:
        async with self.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO dig_history (user_id, kg, timestamp)
                VALUES ($1, $2, $3)
                RETURNING dig_id
                """,
                user_id,
                kg,
                timestamp,
            )

    async def get_user_history(self, user_id: int, limit: int = 10) -> list[DigRecord]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT dig_id, user_id, kg, timestamp
                FROM dig_history
                WHERE user_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [
                DigRecord(
                    dig_id=row["dig_id"],
                    user_id=row["user_id"],
                    kg=row["kg"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    # Leaderboard queries
    async def get_top_day(self, limit: int = 10) -> list[LeaderboardEntry]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.username, COALESCE(SUM(dh.kg), 0) as total_kg, COUNT(dh.dig_id) as digs_count
                FROM users u
                LEFT JOIN dig_history dh ON u.user_id = dh.user_id
                    AND dh.timestamp > EXTRACT(EPOCH FROM NOW()) - 86400
                GROUP BY u.user_id, u.username
                HAVING COALESCE(SUM(dh.kg), 0) > 0
                ORDER BY total_kg DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                LeaderboardEntry(
                    rank=i + 1,
                    username=row["username"] or f"User_{row['user_id']}",
                    total_kg=row["total_kg"],
                    digs_count=row["digs_count"],
                )
                for i, row in enumerate(rows)
            ]

    async def get_top_all(self, limit: int = 10) -> list[LeaderboardEntry]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT u.username, u.total_kg, COUNT(dh.dig_id) as digs_count
                FROM users u
                LEFT JOIN dig_history dh ON u.user_id = dh.user_id
                GROUP BY u.user_id, u.username, u.total_kg
                HAVING u.total_kg > 0
                ORDER BY u.total_kg DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                LeaderboardEntry(
                    rank=i + 1,
                    username=row["username"] or f"User_{row['user_id']}",
                    total_kg=row["total_kg"],
                    digs_count=row["digs_count"],
                )
                for i, row in enumerate(rows)
            ]

    # Maintenance
    async def cleanup_old_history(self, retention_seconds: int) -> int:
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM dig_history
                WHERE timestamp < EXTRACT(EPOCH FROM NOW()) - $1
                """,
                retention_seconds,
            )
            return int(result.split()[-1]) if result else 0


async def init_database(dsn: str) -> None:
    """Initialize database schema."""
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,
                tg_id BIGINT UNIQUE NOT NULL,
                username TEXT,
                total_kg REAL DEFAULT 0.0,
                last_dig_time REAL,
                created_at REAL DEFAULT EXTRACT(EPOCH FROM NOW())
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dig_history (
                dig_id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(user_id) ON DELETE CASCADE,
                kg REAL NOT NULL,
                timestamp REAL NOT NULL
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dig_history_user_timestamp
            ON dig_history (user_id, timestamp DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dig_history_timestamp
            ON dig_history (timestamp)
        """)
    finally:
        await conn.close()