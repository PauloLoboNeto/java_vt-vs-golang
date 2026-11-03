"""FastAPI com o cliente do aiohttp: a mesma API do alvo py-fastapi, sem o httpx."""
import os
import time
from contextlib import asynccontextmanager

_start = time.perf_counter()

import aiohttp
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")


@asynccontextmanager
async def lifespan(app):
    # O padrão do conector é de 100 conexões: um gargalo artificial.
    connector = aiohttp.TCPConnector(limit=0, keepalive_timeout=60)
    app.state.client = aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=10))
    # O formato abaixo é lido por scripts/startup.py.
    print(f"started in {time.perf_counter() - _start:.3f} seconds", flush=True)
    yield
    await app.state.client.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.get("/api/io")
async def io():
    try:
        async with app.state.client.get(UPSTREAM) as r:
            body = await r.read()
            return Response(body, status_code=r.status, media_type="application/json")
    except (aiohttp.ClientError, TimeoutError) as e:
        return PlainTextResponse(repr(e), status_code=502)
