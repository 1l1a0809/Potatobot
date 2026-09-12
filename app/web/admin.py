"""Admin panel routes."""

import time
from aiohttp import web
import aiohttp_jinja2
from app.services import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def require_admin(request: web.Request) -> web.Response | None:
    """Check if user is admin via session cookie."""
    session_id = request.cookies.get("admin_session")
    if not session_id:
        return None

    redis = await get_redis()
    user_id = await redis.get_session(session_id)
    if not user_id:
        return None

    settings = request.app["settings"]
    if user_id not in settings.admin_ids:
        return None

    return user_id


@aiohttp_jinja2.template("admin/login.html")
async def admin_login(request: web.Request):
    if request.method == "POST":
        data = await request.post()
        telegram_id = data.get("telegram_id")
        if telegram_id and telegram_id.isdigit():
            user_id = int(telegram_id)
            settings = request.app["settings"]
            if user_id in settings.admin_ids:
                redis = await get_redis()
                session_id = f"admin_{user_id}_{int(time.time())}"
                await redis.create_session(session_id, user_id)

                response = web.HTTPFound("/admin/")
                response.set_cookie("admin_session", session_id, max_age=86400, httponly=True, secure=True)
                return response

    return {"error": "Неверный Telegram ID или нет прав админа"}


async def admin_logout(request: web.Request):
    session_id = request.cookies.get("admin_session")
    if session_id:
        redis = await get_redis()
        await redis.delete_session(session_id)

    response = web.HTTPFound("/admin/login")
    response.del_cookie("admin_session")
    return response


@aiohttp_jinja2.template("admin/dashboard.html")
async def admin_dashboard(request: web.Request):
    user_id = await require_admin(request)
    if not user_id:
        return web.HTTPFound("/admin/login")

    redis = await get_redis()
    db = request.app["db"]

    # Get stats
    stats = await get_admin_stats(db, redis)

    return {
        "stats": stats,
        "user_id": user_id,
    }


@aiohttp_jinja2.template("admin/users.html")
async def admin_users(request: web.Request):
    user_id = await require_admin(request)
    if not user_id:
        return web.HTTPFound("/admin/login")

    db = request.app["db"]
    page = int(request.query.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    # Get total count
    async with db.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        rows = await conn.fetch(
            """
            SELECT u.user_id, u.tg_id, u.username, u.total_kg, u.last_dig_time, u.created_at,
                   COUNT(dh.dig_id) as digs_count
            FROM users u
            LEFT JOIN dig_history dh ON u.user_id = dh.user_id
            GROUP BY u.user_id, u.tg_id, u.username, u.total_kg, u.last_dig_time, u.created_at
            ORDER BY u.total_kg DESC
            LIMIT $1 OFFSET $2
            """,
            per_page,
            offset,
        )

    users = []
    for row in rows:
        users.append({
            "user_id": row["user_id"],
            "tg_id": row["tg_id"],
            "username": row["username"],
            "total_kg": row["total_kg"],
            "last_dig_time": row["last_dig_time"],
            "created_at": row["created_at"],
            "digs_count": row["digs_count"],
        })

    return {
        "users": users,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
    }


@aiohttp_jinja2.template("admin/user_detail.html")
async def admin_user_detail(request: web.Request):
    user_id = await require_admin(request)
    if not user_id:
        return web.HTTPFound("/admin/login")

    db = request.app["db"]
    target_user_id = int(request.match_info["user_id"])

    async with db.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT user_id, tg_id, username, total_kg, last_dig_time, created_at FROM users WHERE user_id = $1",
            target_user_id,
        )
        if not user:
            raise web.HTTPNotFound(text="User not found")

        digs = await conn.fetch(
            """
            SELECT dig_id, kg, timestamp
            FROM dig_history
            WHERE user_id = $1
            ORDER BY timestamp DESC
            LIMIT 100
            """,
            target_user_id,
        )

        redis = await get_redis()
        achievements = await redis.get_user_achievements(target_user_id)

    return {
        "user": dict(user),
        "digs": [dict(d) for d in digs],
        "achievements": achievements,
    }


async def admin_ban_user(request: web.Request):
    user_id = await require_admin(request)
    if not user_id:
        return web.HTTPFound("/admin/login")

    target_user_id = int(request.match_info["user_id"])
    db = request.app["db"]

    # Soft ban: set a flag or delete user
    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET username = username || '_BANNED' WHERE user_id = $1",
            target_user_id,
        )

    logger.info("user_banned", admin_id=user_id, target_user_id=target_user_id)
    return web.HTTPFound("/admin/users")


async def admin_unban_user(request: web.Request):
    user_id = await require_admin(request)
    if not user_id:
        return web.HTTPFound("/admin/login")

    target_user_id = int(request.match_info["user_id"])
    db = request.app["db"]

    async with db.acquire() as conn:
        await conn.execute(
            "UPDATE users SET username = REPLACE(username, '_BANNED', '') WHERE user_id = $1",
            target_user_id,
        )

    logger.info("user_unbanned", admin_id=user_id, target_user_id=target_user_id)
    return web.HTTPFound("/admin/users")


async def get_admin_stats(db, redis) -> dict:
    """Get admin dashboard statistics."""
    stats = {}

    async with db.acquire() as conn:
        # Total users
        stats["total_users"] = await conn.fetchval("SELECT COUNT(*) FROM users")

        # Active users (dug in last 24h)
        stats["active_24h"] = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM dig_history
            WHERE timestamp > EXTRACT(EPOCH FROM NOW()) - 86400
            """
        )

        # Active users (dug in last 7d)
        stats["active_7d"] = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM dig_history
            WHERE timestamp > EXTRACT(EPOCH FROM NOW()) - 604800
            """
        )

        # Active users (dug in last 30d)
        stats["active_30d"] = await conn.fetchval(
            """
            SELECT COUNT(DISTINCT user_id)
            FROM dig_history
            WHERE timestamp > EXTRACT(EPOCH FROM NOW()) - 2592000
            """
        )

        # Total kg
        stats["total_kg"] = await conn.fetchval("SELECT COALESCE(SUM(total_kg), 0) FROM users")

        # Total digs
        stats["total_digs"] = await conn.fetchval("SELECT COUNT(*) FROM dig_history")

        # Avg kg per dig
        stats["avg_kg"] = await conn.fetchval("SELECT COALESCE(AVG(kg), 0) FROM dig_history")

        # Top user
        top = await conn.fetchrow(
            "SELECT username, total_kg FROM users ORDER BY total_kg DESC LIMIT 1"
        )
        stats["top_user"] = dict(top) if top else None

        # New users today
        today_start = time.time() - (time.time() % 86400)
        stats["new_users_today"] = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE created_at > $1",
            today_start,
        )

    # Redis stats
    redis_info = await redis.client.info("memory")
    stats["redis_memory"] = redis_info.get("used_memory_human", "N/A")

    # Cache hit rate
    hits = await redis.get_counter("cache_hits", {"cache": "leaderboard_day"}) + \
           await redis.get_counter("cache_hits", {"cache": "leaderboard_all"})
    misses = await redis.get_counter("cache_misses", {"cache": "leaderboard_day"}) + \
             await redis.get_counter("cache_misses", {"cache": "leaderboard_all"})
    total_requests = hits + misses
    stats["cache_hit_rate"] = round(hits / total_requests * 100, 1) if total_requests > 0 else 0

    return stats


def setup_admin(app: web.Application):
    app.router.add_get("/admin/login", admin_login)
    app.router.add_post("/admin/login", admin_login)
    app.router.add_get("/admin/logout", admin_logout)
    app.router.add_get("/admin/", admin_dashboard)
    app.router.add_get("/admin/users", admin_users)
    app.router.add_get("/admin/users/{user_id}", admin_user_detail)
    app.router.add_post("/admin/users/{user_id}/ban", admin_ban_user)
    app.router.add_post("/admin/users/{user_id}/unban", admin_unban_user)