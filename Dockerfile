# syntax=docker/dockerfile:1
#
# Image unique : API FastAPI + frontend Svelte compilé (servi par FastAPI sur « / »).
#   docker build -t idf-trains .
#   docker run -p 8000:8000 -e IDF_PRIM_API_KEY=… -v idf-data:/data idf-trains

# --- 1. Frontend : compilation Svelte/Vite -----------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Dépendances Python (uv) -----------------------------------------------------------
FROM python:3.12-slim AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
# Dépendances seules d'abord (couche mise en cache tant que uv.lock ne change pas)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# Puis le code de l'application
COPY README.md ./
COPY src/ src/
RUN uv sync --frozen --no-dev --no-editable

# --- 3. Image finale ----------------------------------------------------------------------
FROM python:3.12-slim
LABEL org.opencontainers.image.title="idf-trains" \
      org.opencontainers.image.description="Prochains trains, trajets et itinéraires Île-de-France Mobilités"

# Utilisateur sans privilèges ; /data contient la base SQLite (volume)
RUN groupadd --system app && useradd --system --gid app --home-dir /app app \
    && mkdir -p /data && chown app:app /data

WORKDIR /app
COPY --from=python-deps --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app data/stations.json /app/data/stations.json
COPY --from=frontend --chown=app:app /build/dist /app/frontend/dist

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    IDF_STATIONS_FILE=/app/data/stations.json \
    IDF_FRONTEND_DIR=/app/frontend/dist \
    IDF_DB_PATH=/data/journeys.db

USER app
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Un seul worker : cache mémoire et SQLite sont propres au processus.
# Pour plusieurs workers/instances, utilisez Redis (IDF_REDIS_URL, voir docker-compose.yml).
CMD ["uvicorn", "idf_trains.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
