"""Health check endpoints."""

from aiohttp import web
from app.database import Database


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


def setup_health(app: web.Application) -> None:
    app.router.add_get("/health", health_check)
    app.router.add_get("/ready", readiness_check)
    app.router.add_get("/", health_check)  # For Render keep-alive