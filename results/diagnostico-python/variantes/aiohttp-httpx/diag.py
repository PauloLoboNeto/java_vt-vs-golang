"""aiohttp como servidor, com httpx como cliente."""
import os
import httpx
from aiohttp import web
UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")

async def health(request):
    return web.Response(text="ok")

async def io(request):
    try:
        r = await request.app["client"].get(UPSTREAM)
    except httpx.HTTPError as e:
        return web.Response(text=repr(e), status=502)
    return web.Response(body=r.content, status=r.status_code, content_type="application/json")

async def ctx(app):
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None, keepalive_expiry=60)
    app["client"] = httpx.AsyncClient(limits=limits, timeout=10)
    yield
    await app["client"].aclose()

async def create_app():
    app = web.Application()
    app.cleanup_ctx.append(ctx)
    app.router.add_get("/health", health)
    app.router.add_get("/api/io", io)
    return app
