"""Clan/Team service for group gameplay."""

import time
import uuid
from dataclasses import dataclass
from typing import Optional, List
from app.database import Database
from app.services import get_redis
from app.utils.logging import get_logger
from app.config import get_settings

logger = get_logger(__name__)


@dataclass
class Clan:
    clan_id: int
    name: str
    tag: str
    owner_id: int
    total_kg: float
    member_count: int
    created_at: float
    description: Optional[str] = None


@dataclass
class ClanMember:
    user_id: int
    clan_id: int
    role: str  # owner, officer, member
    joined_at: float
    contributed_kg: float


@dataclass
class ClanInvite:
    invite_id: str
    clan_id: int
    inviter_id: int
    invitee_id: int
    created_at: float
    expires_at: float


class ClanService:
    def __init__(self, db: Database):
        self.db = db
        self.settings = get_settings()
        self._redis = None

    @property
    async def redis(self):
        if self._redis is None:
            self._redis = await get_redis()
        return self._redis

    # ===== Clan Management =====
    async def create_clan(self, owner_id: int, name: str, tag: str, description: str = "") -> dict:
        """Create a new clan."""
        # Validate
        if len(name) < 3 or len(name) > 32:
            return {"success": False, "error": "Название клана: 3-32 символа"}
        if len(tag) < 2 or len(tag) > 8:
            return {"success": False, "error": "Тег клана: 2-8 символов"}
        if not tag.isalnum():
            return {"success": False, "error": "Тег только буквы и цифры"}

        # Check if user already in clan
        existing = await self.get_user_clan(owner_id)
        if existing:
            return {"success": False, "error": "Ты уже в клане"}

        # Check name/tag uniqueness
        if await self._clan_name_exists(name):
            return {"success": False, "error": "Клан с таким названием уже существует"}
        if await self._clan_tag_exists(tag):
            return {"success": False, "error": "Клан с таким тегом уже существует"}

        # Create clan
        clan_id = await self._create_clan_db(owner_id, name, tag.upper(), description)
        
        # Add owner as member
        await self._add_member_db(owner_id, clan_id, "owner")

        # Update user's clan_id
        await self._set_user_clan(owner_id, clan_id)

        logger.info("clan_created", clan_id=clan_id, owner_id=owner_id, name=name, tag=tag)
        return {"success": True, "clan_id": clan_id}

    async def _create_clan_db(self, owner_id: int, name: str, tag: str, description: str) -> int:
        async with self.db.acquire() as conn:
            return await conn.fetchval(
                """
                INSERT INTO clans (name, tag, owner_id, total_kg, member_count, created_at, description)
                VALUES ($1, $2, $3, 0.0, 1, $4, $5)
                RETURNING clan_id
                """,
                name, tag, owner_id, time.time(), description,
            )

    async def _clan_name_exists(self, name: str) -> bool:
        async with self.db.acquire() as conn:
            return await conn.fetchval(
                "SELECT 1 FROM clans WHERE LOWER(name) = LOWER($1)", name
            ) is not None

    async def _clan_tag_exists(self, tag: str) -> bool:
        async with self.db.acquire() as conn:
            return await conn.fetchval(
                "SELECT 1 FROM clans WHERE tag = $1", tag.upper()
            ) is not None

    # ===== Membership =====
    async def get_user_clan(self, user_id: int) -> Optional[Clan]:
        """Get clan for user."""
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT c.clan_id, c.name, c.tag, c.owner_id, c.total_kg, c.member_count, c.created_at, c.description
                FROM clans c
                JOIN clan_members cm ON c.clan_id = cm.clan_id
                WHERE cm.user_id = $1
                """,
                user_id,
            )
            if row:
                return Clan(**dict(row))
        return None

    async def get_clan(self, clan_id: int) -> Optional[Clan]:
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT clan_id, name, tag, owner_id, total_kg, member_count, created_at, description FROM clans WHERE clan_id = $1",
                clan_id,
            )
            if row:
                return Clan(**dict(row))
        return None

    async def get_clan_members(self, clan_id: int) -> List[ClanMember]:
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cm.user_id, cm.clan_id, cm.role, cm.joined_at, cm.contributed_kg,
                       u.username, u.total_kg
                FROM clan_members cm
                JOIN users u ON cm.user_id = u.user_id
                WHERE cm.clan_id = $1
                ORDER BY 
                    CASE cm.role WHEN 'owner' THEN 0 WHEN 'officer' THEN 1 ELSE 2 END,
                    cm.contributed_kg DESC
                """,
                clan_id,
            )
            return [ClanMember(**dict(row)) for row in rows]

    async def _add_member_db(self, user_id: int, clan_id: int, role: str = "member") -> None:
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clan_members (user_id, clan_id, role, joined_at, contributed_kg)
                VALUES ($1, $2, $3, $4, 0.0)
                """,
                user_id, clan_id, role, time.time(),
            )

    async def _set_user_clan(self, user_id: int, clan_id: int) -> None:
        async with self.db.acquire() as conn:
            await conn.execute(
                "UPDATE users SET clan_id = $1 WHERE user_id = $2",
                clan_id, user_id,
            )

    async def _remove_user_clan(self, user_id: int) -> None:
        async with self.db.acquire() as conn:
            await conn.execute(
                "UPDATE users SET clan_id = NULL WHERE user_id = $1",
                user_id,
            )

    # ===== Invites =====
    async def invite_user(self, inviter_id: int, invitee_username: str) -> dict:
        """Invite user to clan."""
        clan = await self.get_user_clan(inviter_id)
        if not clan:
            return {"success": False, "error": "Ты не в клане"}

        # Check permissions
        member = await self.get_member(clan.clan_id, inviter_id)
        if not member or member.role not in ("owner", "officer"):
            return {"success": False, "error": "Нет прав на приглашение"}

        # Find invitee
        async with self.db.acquire() as conn:
            invitee = await conn.fetchrow(
                "SELECT user_id FROM users WHERE LOWER(username) = LOWER($1)",
                invitee_username.lstrip("@"),
            )

        if not invitee:
            return {"success": False, "error": "Пользователь не найден"}

        invitee_id = invitee["user_id"]

        # Check if already in clan
        if await self.get_user_clan(invitee_id):
            return {"success": False, "error": "Пользователь уже в клане"}

        # Check existing invite
        existing = await self._get_pending_invite(clan.clan_id, invitee_id)
        if existing:
            return {"success": False, "error": "Приглашение уже отправлено"}

        # Create invite
        invite_id = str(uuid.uuid4())[:8]
        await self._create_invite_db(invite_id, clan.clan_id, inviter_id, invitee_id)

        logger.info("clan_invite_sent", clan_id=clan.clan_id, inviter_id=inviter_id, invitee_id=invitee_id)
        return {"success": True, "invite_id": invite_id}

    async def _create_invite_db(self, invite_id: str, clan_id: int, inviter_id: int, invitee_id: int) -> None:
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO clan_invites (invite_id, clan_id, inviter_id, invitee_id, created_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                invite_id, clan_id, inviter_id, invitee_id, time.time(), time.time() + 86400 * 7,
            )

    async def _get_pending_invite(self, clan_id: int, invitee_id: int) -> bool:
        async with self.db.acquire() as conn:
            return await conn.fetchval(
                "SELECT 1 FROM clan_invites WHERE clan_id = $1 AND invitee_id = $2 AND expires_at > $3",
                clan_id, invitee_id, time.time(),
            ) is not None

    async def accept_invite(self, user_id: int, invite_id: str) -> dict:
        """Accept clan invite."""
        async with self.db.acquire() as conn:
            invite = await conn.fetchrow(
                "SELECT clan_id, invitee_id FROM clan_invites WHERE invite_id = $1 AND expires_at > $2",
                invite_id, time.time(),
            )

        if not invite:
            return {"success": False, "error": "Приглашение не найдено или истекло"}

        if invite["invitee_id"] != user_id:
            return {"success": False, "error": "Это не твоё приглашение"}

        # Check if already in clan
        if await self.get_user_clan(user_id):
            return {"success": False, "error": "Ты уже в клане"}

        # Add to clan
        await self._add_member_db(user_id, invite["clan_id"], "member")
        await self._set_user_clan(user_id, invite["clan_id"])

        # Update clan member count
        async with self.db.acquire() as conn:
            await conn.execute(
                "UPDATE clans SET member_count = member_count + 1 WHERE clan_id = $1",
                invite["clan_id"],
            )
            # Delete invite
            await conn.execute("DELETE FROM clan_invites WHERE invite_id = $1", invite_id)

        # Update cache
        redis = await self.redis
        await redis.invalidate_leaderboard("clan", 10)

        logger.info("clan_invite_accepted", clan_id=invite["clan_id"], user_id=user_id)
        return {"success": True, "clan_id": invite["clan_id"]}

    async def decline_invite(self, user_id: int, invite_id: str) -> dict:
        async with self.db.acquire() as conn:
            invite = await conn.fetchrow(
                "SELECT invitee_id FROM clan_invites WHERE invite_id = $1", invite_id,
            )
        if not invite or invite["invitee_id"] != user_id:
            return {"success": False, "error": "Приглашение не найдено"}

        async with self.db.acquire() as conn:
            await conn.execute("DELETE FROM clan_invites WHERE invite_id = $1", invite_id)
        return {"success": True}

    async def get_pending_invites(self, user_id: int) -> List[dict]:
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ci.invite_id, ci.clan_id, ci.created_at, ci.expires_at,
                       c.name, c.tag, u.username as inviter_name
                FROM clan_invites ci
                JOIN clans c ON ci.clan_id = c.clan_id
                JOIN users u ON ci.inviter_id = u.user_id
                WHERE ci.invitee_id = $1 AND ci.expires_at > $2
                ORDER BY ci.created_at DESC
                """,
                user_id, time.time(),
            )
            return [dict(row) for row in rows]

    # ===== Leave / Kick =====
    async def leave_clan(self, user_id: int) -> dict:
        clan = await self.get_user_clan(user_id)
        if not clan:
            return {"success": False, "error": "Ты не в клане"}

        member = await self.get_member(clan.clan_id, user_id)
        if member and member.role == "owner":
            # Owner can't leave, must transfer or disband
            return {"success": False, "error": "Владелец не может покинуть клан. Передай права или распусти клан."}

        await self._remove_member(user_id, clan.clan_id)
        return {"success": True}

    async def _remove_member(self, user_id: int, clan_id: int) -> None:
        async with self.db.acquire() as conn:
            await conn.execute(
                "DELETE FROM clan_members WHERE user_id = $1 AND clan_id = $2",
                user_id, clan_id,
            )
            await conn.execute(
                "UPDATE clans SET member_count = member_count - 1 WHERE clan_id = $1",
                clan_id,
            )
        await self._remove_user_clan(user_id)

    async def kick_member(self, kicker_id: int, target_id: int) -> dict:
        clan = await self.get_user_clan(kicker_id)
        if not clan:
            return {"success": False, "error": "Ты не в клане"}

        kicker_member = await self.get_member(clan.clan_id, kicker_id)
        target_member = await self.get_member(clan.clan_id, target_id)

        if not target_member:
            return {"success": False, "error": "Пользователь не в клане"}

        # Check permissions
        if kicker_member.role == "member":
            return {"success": False, "error": "Нет прав"}

        # Can't kick owner or same/higher role
        role_order = {"owner": 3, "officer": 2, "member": 1}
        if role_order.get(kicker_member.role, 0) <= role_order.get(target_member.role, 0):
            return {"success": False, "error": "Нельзя кикнуть этого пользователя"}

        await self._remove_member(target_id, clan.clan_id)
        return {"success": True}

    async def transfer_ownership(self, owner_id: int, new_owner_id: int) -> dict:
        clan = await self.get_user_clan(owner_id)
        if not clan or clan.owner_id != owner_id:
            return {"success": False, "error": "Ты не владелец клана"}

        new_owner = await self.get_member(clan.clan_id, new_owner_id)
        if not new_owner:
            return {"success": False, "error": "Пользователь не в клане"}

        async with self.db.acquire() as conn:
            await conn.execute(
                "UPDATE clans SET owner_id = $1 WHERE clan_id = $2", new_owner_id, clan.clan_id,
            )
            await conn.execute(
                "UPDATE clan_members SET role = 'owner' WHERE user_id = $1 AND clan_id = $2", new_owner_id, clan.clan_id,
            )
            await conn.execute(
                "UPDATE clan_members SET role = 'member' WHERE user_id = $1 AND clan_id = $2", owner_id, clan.clan_id,
            )

        return {"success": True}

    async def disband_clan(self, owner_id: int) -> dict:
        clan = await self.get_user_clan(owner_id)
        if not clan or clan.owner_id != owner_id:
            return {"success": False, "error": "Ты не владелец клана"}

        async with self.db.acquire() as conn:
            # Remove all members
            await conn.execute("DELETE FROM clan_members WHERE clan_id = $1", clan.clan_id)
            await conn.execute("UPDATE users SET clan_id = NULL WHERE clan_id = $1", clan.clan_id)
            await conn.execute("DELETE FROM clan_invites WHERE clan_id = $1", clan.clan_id)
            await conn.execute("DELETE FROM clans WHERE clan_id = $1", clan.clan_id)

        # Invalidate cache
        redis = await self.redis
        await redis.invalidate_leaderboard("clan", 10)

        return {"success": True}

    # ===== Clan Stats & Contributions =====
    async def get_member(self, clan_id: int, user_id: int) -> Optional[ClanMember]:
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT cm.user_id, cm.clan_id, cm.role, cm.joined_at, cm.contributed_kg
                FROM clan_members cm
                WHERE cm.clan_id = $1 AND cm.user_id = $2
                """,
                clan_id, user_id,
            )
            if row:
                return ClanMember(**dict(row))
        return None

    async def add_contribution(self, user_id: int, kg: float) -> None:
        """Add kg to clan total when user digs."""
        clan = await self.get_user_clan(user_id)
        if not clan:
            return

        async with self.db.acquire() as conn:
            await conn.execute(
                """
                UPDATE clan_members 
                SET contributed_kg = contributed_kg + $1
                WHERE user_id = $2 AND clan_id = $3
                """,
                kg, user_id, clan.clan_id,
            )
            await conn.execute(
                "UPDATE clans SET total_kg = total_kg + $1 WHERE clan_id = $2",
                kg, clan.clan_id,
            )

        # Invalidate cache
        redis = await self.redis
        await redis.invalidate_leaderboard("clan", 10)

    # ===== Clan Leaderboards =====
    async def get_top_clans(self, limit: int = 10) -> List[dict]:
        redis = await self.redis
        cached = await redis.get_leaderboard("clan", limit)
        if cached is not None:
            return cached

        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT clan_id, name, tag, total_kg, member_count
                FROM clans
                WHERE member_count > 0
                ORDER BY total_kg DESC
                LIMIT $1
                """,
                limit,
            )
            result = [
                {
                    "rank": i + 1,
                    "clan_id": row["clan_id"],
                    "name": row["name"],
                    "tag": row["tag"],
                    "total_kg": row["total_kg"],
                    "member_count": row["member_count"],
                }
                for i, row in enumerate(rows)
            ]

        await redis.set_leaderboard("clan", limit, result, self.settings.leaderboard_cache_ttl)
        return result


# Global instance
_clan_service = None


def get_clan_service(db: Database = None) -> ClanService:
    global _clan_service
    if _clan_service is None and db is not None:
        _clan_service = ClanService(db)
    return _clan_service