"""REST API for frontend."""

from aiohttp import web
from app.services import get_redis
from app.utils.logging import get_logger

logger = get_logger(__name__)


async def require_auth(request: web.Request) -> int | None:
    """Check authentication via Telegram initData or session."""
    # Check for Telegram Web App initData
    init_data = request.headers.get("X-Telegram-Init-Data")
    if init_data:
        # Validate initData (simplified - in production use proper validation)
        # For now, extract user_id from initData
        import urllib.parse
        params = dict(urllib.parse.parse_qsl(init_data))
        if "user" in params:
            import json
            user_data = json.loads(params["user"])
            return user_data.get("id")

    # Check session cookie
    session_id = request.cookies.get("user_session")
    if session_id:
        redis = await get_redis()
        user_id = await redis.get_session(session_id)
        if user_id:
            return user_id

    return None


async def api_user_stats(request: web.Request) -> web.Response:
    """Get current user stats."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    db = request.app["db"]
    user = await db.get_user_by_tg_id(user_id)

    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    # Get recent history
    history = await db.get_user_history(user.user_id, 10)

    return web.json_response({
        "user": {
            "user_id": user.user_id,
            "tg_id": user.tg_id,
            "username": user.username,
            "total_kg": user.total_kg,
            "last_dig_time": user.last_dig_time,
            "created_at": user.created_at,
        },
        "history": [
            {"dig_id": h.dig_id, "kg": h.kg, "timestamp": h.timestamp}
            for h in history
        ],
    })


async def api_leaderboard(request: web.Request) -> web.Response:
    """Get leaderboard."""
    period = request.query.get("period", "day")  # day or all
    limit = min(int(request.query.get("limit", 10)), 100)

    db = request.app["db"]

    if period == "day":
        rows = await db.get_top_day(limit)
    else:
        rows = await db.get_top_all(limit)

    return web.json_response({
        "period": period,
        "entries": [
            {
                "rank": e.rank,
                "username": e.username,
                "total_kg": e.total_kg,
                "digs_count": e.digs_count,
            }
            for e in rows
        ],
    })


async def api_daily_bonus(request: web.Request) -> web.Response:
    """Get daily bonus status."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    from app.services import get_daily_bonus_service
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = request.app["db"]

    status = await daily_bonus_service.get_status(user_id)
    return web.json_response(status)


async def api_claim_daily_bonus(request: web.Request) -> web.Response:
    """Claim daily bonus."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    from app.services import get_daily_bonus_service
    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = request.app["db"]

    result = await daily_bonus_service.claim(user_id)
    return web.json_response(result)


async def api_achievements(request: web.Request) -> web.Response:
    """Get user achievements."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    from app.services import get_achievement_service
    db = request.app["db"]
    user = await db.get_user_by_tg_id(user_id)

    if not user:
        return web.json_response({"error": "User not found"}, status=404)

    achievement_service = get_achievement_service()
    user_achievements = await achievement_service.get_user_achievements(user.user_id)
    all_achievements = achievement_service.get_all_achievements()

    return web.json_response({
        "unlocked": [
            {
                "id": ach_id,
                "name": ach.name,
                "description": ach.description,
                "icon": ach.icon,
            }
            for ach_id in user_achievements
            if (ach := achievement_service.get_achievement(ach_id))
        ],
        "locked": [
            {
                "id": ach.id,
                "name": ach.name,
                "description": ach.description,
                "icon": ach.icon,
            }
            for ach in all_achievements
            if ach.id not in user_achievements
        ],
    })


async def api_dig(request: web.Request) -> web.Response:
    """Perform a dig (for Web App)."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    dig_service = request.app["bot"].dig_service
    username = request.headers.get("X-Telegram-Username")

    try:
        result = await dig_service.perform_dig(user_id, username)
        return web.json_response(result)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


def setup_api(app: web.Application):
    """Setup API routes."""
    app.router.add_get("/api/v1/user/stats", api_user_stats)
    app.router.add_get("/api/v1/leaderboard", api_leaderboard)
    app.router.add_get("/api/v1/daily-bonus", api_daily_bonus)
    app.router.add_post("/api/v1/daily-bonus/claim", api_claim_daily_bonus)
    app.router.add_get("/api/v1/achievements", api_achievements)
    app.router.add_post("/api/v1/dig", api_dig)