FROM python:3.15.2-slim-bookworm
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements.txt
COPY app.py .
# Um processo por vCPU: o GIL impede um processo só de usar os 2 vCPU.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--loop", "uvloop", "--http", "httptools", "--backlog", "65535", "--timeout-keep-alive", "60", "--no-access-log"]
