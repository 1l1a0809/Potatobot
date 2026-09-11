"""Web server setup."""

from aiohttp import web
from app.web.health import setup_health
from app.web.metrics import setup_metrics


async def create_web_app(db) -> web.Application:
    app = web.Application()
    app["db"] = db
    
    setup_health(app)
    setup_metrics(app)
    
    return app


async def run_web_server(app: web.Application, host: str, port: int) -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner