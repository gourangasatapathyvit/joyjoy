# joyjoy — single image: builds the React SPA, then runs the FastAPI backend which
# serves BOTH the SPA and the /v1 API on :8080. Multi-stage so the final image has
# no Node toolchain. The backend expects the built SPA at <repo>/frontend/dist
# (app/main.py resolves it as app/../../frontend/dist), so we lay the code out as
# /app/backend + /app/frontend/dist and run from /app/backend.

# ---------- Stage 1: build the React SPA ----------
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build      # -> /frontend/dist

# ---------- Stage 2: backend (FastAPI + deepagents) ----------
FROM python:3.13-slim AS app
# uv installs deps fast; uvx is used by the duckduckgo web-search MCP. curl backs the healthcheck.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
# LibreOffice (headless) powers office→PDF previews (app/media.py: .doc/.docx/.xls/
# .xlsx/.ppt/.pptx). It's the bulk of the image (~hundreds of MB); drop the three
# libreoffice-* + fonts packages if you don't need office previews.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates curl \
      libreoffice-writer libreoffice-calc libreoffice-impress fonts-liberation \
 && rm -rf /var/lib/apt/lists/*
ENV UV_SYSTEM_PYTHON=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=prod \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8080

WORKDIR /app/backend
COPY backend/ /app/backend/
# Editable install keeps app/ in place (so app/main.py finds ../../frontend/dist)
# while installing all dependencies into the system interpreter.
RUN uv pip install --system -e .

# the built SPA the backend serves (relative to the backend package: ../../frontend/dist)
COPY --from=frontend /frontend/dist /app/frontend/dist

EXPOSE 8080
# WORKSPACE_ROOT (agent files) is mounted at /data in compose; ensure it exists so
# a plain `docker run` without a volume still works. The app makedirs subdirs on demand.
RUN mkdir -p /data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]