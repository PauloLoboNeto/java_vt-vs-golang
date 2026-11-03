FROM bench/py-fastapi
COPY diag.py .
CMD ["uvicorn", "diag:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--loop", "uvloop", "--http", "httptools", "--backlog", "65535", "--timeout-keep-alive", "60", "--no-access-log"]
