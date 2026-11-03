"""FastAPI como servidor, com o cliente do aiohttp no lugar do httpx."""
import os
from contextlib import asynccontextmanager
import aiohttp
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse
UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")

@asynccontextmanager
async def lifespan(app):
    app.state.client = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0, keepalive_timeout=60), timeout=aiohttp.ClientTimeout(total=10))
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
            return Response(await r.read(), status_code=r.status, media_type="application/json")
    except (aiohttp.ClientError, TimeoutError) as e:
        return PlainTextResponse(repr(e), status_code=502)
