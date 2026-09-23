FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FIND_FACE_DATA=/data \
    FIND_FACE_PORT=8765
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 findface \
    && useradd --uid 10001 --gid findface --no-create-home findface \
    && mkdir /data && chown findface:findface /data
COPY requirements.lock ./
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.lock
COPY backend ./backend
COPY web ./web
COPY scripts ./scripts
USER findface
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
