"""Prometheus metrics endpoint."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest
from aiohttp import web

DIG_COMMANDS = Counter(
    "potatobot_dig_commands_total",
    "Total dig commands",
    ["status"],
)
DIG_KG = Histogram("potatobot_dig_kg", "Potato weight per dig")
ACTIVE_USERS = Gauge("potatobot_active_users", "Users with digs in last 24h")
DB_QUERY_DURATION = Histogram(
    "potatobot_db_query_duration_seconds",
    "DB query duration",
)
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


async def metrics_handler(request: web.Request) -> web.Response:
    return web.Response(body=generate_latest(), content_type="text/plain")


def setup_metrics(app: web.Application) -> None:
    app.router.add_get("/metrics", metrics_handler)