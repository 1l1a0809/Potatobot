"""User service for user management."""

import time
from app.database import Database, User
from app.exceptions import UserNotFoundError
from app.utils.logging import get_logger

logger = get_logger(__name__)


class UserService:
    def __init__(self, db: Database):
        self.db = db

    async def get_or_create_user(self, tg_id: int, username: str | None) -> User:
        user = await self.db.get_or_create_user(tg_id, username)
        logger.debug("user_get_or_create", tg_id=tg_id, user_id=user.user_id)
        return user

    async def get_user(self, tg_id: int) -> User:
        user = await self.db.get_user_by_tg_id(tg_id)
        if user is None:
            raise UserNotFoundError(f"User {tg_id} not found")
        return user

    async def update_dig_stats(self, user_id: int, kg: float) -> User:
        timestamp = time.time()
        user = await self.db.update_user_dig(user_id, kg, timestamp)
        logger.info("user_dig_updated", user_id=user_id, kg=kg, total_kg=user.total_kg)
        return user