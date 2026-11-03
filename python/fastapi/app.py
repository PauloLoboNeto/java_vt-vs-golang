"""FastAPI com httpx: a pilha assíncrona mais comum em Python. Sem trabalho de CPU no handler."""
import os
import time
from contextlib import asynccontextmanager

_start = time.perf_counter()

import httpx
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")


@asynccontextmanager
async def lifespan(app):
    # O padrão do httpx é de 100 conexões e timeout de 5s: um gargalo artificial e um erro
    # garantido, já que a API externa leva exatamente 5s.
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None, keepalive_expiry=60)
    app.state.client = httpx.AsyncClient(limits=limits, timeout=10)
    # O formato abaixo é lido por scripts/startup.py.
    print(f"started in {time.perf_counter() - _start:.3f} seconds", flush=True)
    yield
    await app.state.client.aclose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health():
    return PlainTextResponse("ok")


@app.get("/api/io")
async def io():
    try:
        r = await app.state.client.get(UPSTREAM)
    except httpx.HTTPError as e:
        return PlainTextResponse(repr(e), status_code=502)
    return Response(r.content, status_code=r.status_code, media_type="application/json")
