"""Flask com requests: código síncrono. A concorrência vem do worker do gunicorn (gevent ou threads)."""
import os
import time

_start = time.perf_counter()

import requests
from flask import Flask, Response
from requests.adapters import HTTPAdapter

UPSTREAM = os.environ.get("UPSTREAM_URL", "http://mock-api:8080/delay")

session = requests.Session()
# O padrão do pool é de 10 conexões: acima disso, cada chamada abriria e descartaria uma conexão.
session.mount("http://", HTTPAdapter(pool_connections=1, pool_maxsize=20000, max_retries=0))

app = Flask(__name__)


@app.get("/health")
def health():
    return "ok"


@app.get("/api/io")
def io():
    try:
        r = session.get(UPSTREAM, timeout=10)
    except requests.RequestException as e:
        return repr(e), 502
    return Response(r.content, status=r.status_code, content_type="application/json")


# O formato abaixo é lido por scripts/startup.py.
print(f"started in {time.perf_counter() - _start:.3f} seconds", flush=True)
