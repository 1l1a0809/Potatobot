"""Web server setup."""

from datetime import datetime
from aiohttp import web
import aiohttp_jinja2
import jinja2

from app.web.routes import setup_routes
from app.web.admin import setup_admin
from app.services.achievement_service import get_achievement_service


def datetime_filter(value):
    """Convert timestamp to readable datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(value)).strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return str(value)


async def create_web_app(db, redis, settings, bot=None) -> web.Application:
    app = web.Application()
    app["db"] = db
    app["redis"] = redis
    app["settings"] = settings
    if bot:
        app["bot"] = bot

    # Setup Jinja2 with filters
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader("app/web/templates"),
        filters={"datetime": datetime_filter},
    )

    # Add achievements map to templates
    @aiohttp_jinja2.template("admin/user_detail.html")
    async def admin_user_detail_with_achievements(request):
        from app.web.admin import admin_user_detail
        result = await admin_user_detail(request)
        if isinstance(result, dict):
            achievement_service = get_achievement_service()
            result["achievements_map"] = {a.id: a for a in achievement_service.get_all_achievements()}
        return result

    # Override the route
    app.router.add_get("/admin/users/{user_id}", admin_user_detail_with_achievements)

    # Setup all routes
    setup_routes(app)
    setup_admin(app)

    return app


async def run_web_server(app: web.Application, host: str, port: int):
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner


__all__ = [
    "create_web_app",
    "run_web_server",
]