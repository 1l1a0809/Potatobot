"""Prometheus metrics with DAU/WAU/Retention."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from aiohttp import web

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


async def metrics_handler(request: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), content_type="text/plain")


def setup_metrics(app: web.Application) -> None:
    app.router.add_get("/metrics", metrics_handler)