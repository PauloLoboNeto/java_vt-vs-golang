FROM bench/py-aiohttp
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check httpx==0.28.1
COPY diag.py .
CMD ["gunicorn", "diag:create_app", "--bind", "0.0.0.0:8080", "--workers", "2", "--worker-class", "aiohttp.GunicornUVLoopWebWorker", "--backlog", "65535", "--keep-alive", "60"]
