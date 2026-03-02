FROM python:3.12-slim AS base

# System deps (KLayout for DRC execution)
RUN apt-get update && \
    apt-get install -y --no-install-recommends klayout libgl1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Application code
COPY backend/ backend/

# Data volume mount point
RUN mkdir -p /app/data
VOLUME /app/data

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Frontend build stage ---
FROM node:22-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- Production image ---
FROM base AS production
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
