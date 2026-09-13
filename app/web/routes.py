"""Web routes: health, metrics, api."""

from datetime import datetime
from aiohttp import web
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from app.database import Database
from app.services.redis_service import get_redis
from app.services import get_daily_bonus_service, get_achievement_service
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ===== Prometheus Metrics =====

# Dig metrics
DIG_COMMANDS = Counter(
    "potatobot_dig_commands_total",
    "Total dig commands",
    ["status"],
)
DIG_KG = Histogram(
    "potatobot_dig_kg",
    "Potato weight per dig",
    buckets=[1, 2, 3, 4, 5, 6, 7]
)
DIG_KG_BY_USER = Histogram(
    "potatobot_dig_weight_by_user_kg",
    "Weight distribution per user",
    ["user_id"],
    buckets=[1, 2, 3, 4, 5, 6, 7]
)

# User metrics
ACTIVE_USERS_DAILY = Gauge("potatobot_active_users_daily", "DAU")
ACTIVE_USERS_WEEKLY = Gauge("potatobot_active_users_weekly", "WAU")
ACTIVE_USERS_MONTHLY = Gauge("potatobot_active_users_monthly", "MAU")
RETENTION_D1 = Gauge("potatobot_retention_day1", "Day 1 retention")
RETENTION_D7 = Gauge("potatobot_retention_day7", "Day 7 retention")
RETENTION_D30 = Gauge("potatobot_retention_day30", "Day 30 retention")

# Cache metrics
CACHE_HITS = Counter(
    "potatobot_cache_hits_total",
    "Cache hits",
    ["cache_name"],
)
CACHE_MISSES = Counter(
    "potatobot_cache_misses_total",
    "Cache misses",
    ["cache_name"],
)

# DB metrics
DB_QUERY_DURATION = Histogram(
    "potatobot_db_query_duration_seconds",
    "DB query duration",
)
DB_POOL_USAGE = Gauge("potatobot_db_pool_usage", "Pool usage", ["state"])
DB_QUERY_ERRORS = Counter("potatobot_db_query_errors_total", "DB errors", ["query"])

# Error metrics
ERRORS_TOTAL = Counter("potatobot_errors_total", "Errors", ["type", "handler"])

# Daily bonus metrics
DAILY_BONUS_CLAIMS = Counter("potatobot_daily_bonus_claims_total", "Daily bonus claims", ["status"])
DAILY_BONUS_STREAK = Gauge("potatobot_daily_bonus_streak", "Current streak", ["user_id"])

# Achievement metrics
ACHIEVEMENTS_UNLOCKED = Counter("potatobot_achievements_unlocked_total", "Achievements unlocked", ["achievement_id"])


# ===== Health Endpoints =====

async def health_check(request: web.Request) -> web.Response:
    db: Database = request.app["db"]
    healthy = await db.health_check()
    if healthy:
        return web.json_response({"status": "healthy", "database": "connected"})
    return web.json_response(
        {"status": "unhealthy", "database": "disconnected"},
        status=503,
    )


async def readiness_check(request: web.Request) -> web.Response:
    return web.json_response({"status": "ready"})


# ===== Metrics Endpoint =====

async def metrics_handler(request: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), content_type="text/plain")


# ===== API Endpoints =====

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

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = request.app["db"]

    status = await daily_bonus_service.get_status(user_id)
    return web.json_response(status)


async def api_claim_daily_bonus(request: web.Request) -> web.Response:
    """Claim daily bonus."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

    daily_bonus_service = get_daily_bonus_service()
    daily_bonus_service.db = request.app["db"]

    result = await daily_bonus_service.claim(user_id)
    return web.json_response(result)


async def api_achievements(request: web.Request) -> web.Response:
    """Get user achievements."""
    user_id = await require_auth(request)
    if not user_id:
        return web.json_response({"error": "Unauthorized"}, status=401)

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


# ===== Route Setup Functions =====

def setup_health(app: web.Application) -> None:
    app.router.add_get("/health", health_check)
    app.router.add_get("/ready", readiness_check)
    app.router.add_get("/", health_check)  # For Render keep-alive


def setup_metrics(app: web.Application) -> None:
    app.router.add_get("/metrics", metrics_handler)


def setup_api(app: web.Application):
    """Setup API routes."""
    app.router.add_get("/api/v1/user/stats", api_user_stats)
    app.router.add_get("/api/v1/leaderboard", api_leaderboard)
    app.router.add_get("/api/v1/daily-bonus", api_daily_bonus)
    app.router.add_post("/api/v1/daily-bonus/claim", api_claim_daily_bonus)
    app.router.add_get("/api/v1/achievements", api_achievements)
    app.router.add_post("/api/v1/dig", api_dig)


def setup_routes(app: web.Application) -> None:
    """Setup all routes."""
    setup_health(app)
    setup_metrics(app)
    setup_api(app)


__all__ = [
    "health_check",
    "readiness_check",
    "metrics_handler",
    "setup_health",
    "setup_metrics",
    "setup_api",
    "setup_routes",
]