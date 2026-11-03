FROM python:3.15.2-slim-bookworm
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir --root-user-action=ignore --disable-pip-version-check -r requirements.txt
COPY app.py .
# Um processo por vCPU: o GIL impede um processo só de usar os 2 vCPU.
CMD ["gunicorn", "app:create_app", "--bind", "0.0.0.0:8080", "--workers", "2", "--worker-class", "aiohttp.GunicornUVLoopWebWorker", "--backlog", "65535", "--keep-alive", "60"]
