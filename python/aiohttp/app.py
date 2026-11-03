"""aiohttp como servidor e como cliente: asyncio com menos camadas. Sem trabalho de CPU no handler."""
import os
import time

_start = time.perf_counter()

import aiohttp
from aiohttp import web

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")


async def health(request):
    return web.Response(text="ok")


async def io(request):
    try:
        async with request.app["client"].get(UPSTREAM) as r:
            body = await r.read()
            return web.Response(body=body, status=r.status, content_type="application/json")
    except (aiohttp.ClientError, TimeoutError) as e:
        return web.Response(text=repr(e), status=502)


async def client_ctx(app):
    # O padrão do conector é de 100 conexões: um gargalo artificial.
    connector = aiohttp.TCPConnector(limit=0, keepalive_timeout=60)
    app["client"] = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10))
    # O formato abaixo é lido por scripts/startup.py.
    print(f"started in {time.perf_counter() - _start:.3f} seconds", flush=True)
    yield
    await app["client"].close()


async def create_app():
    app = web.Application()
    app.cleanup_ctx.append(client_ctx)
    app.router.add_get("/health", health)
    app.router.add_get("/api/io", io)
    return app
