FROM node:24-bookworm-slim AS web
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV NEXT_PUBLIC_API_URL=/api
ARG WEB_URL
ENV NEXT_PUBLIC_WEB_URL=${WEB_URL}
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ ./backend/
COPY --from=web /build/frontend/out ./frontend/out
WORKDIR /app/backend
CMD ["sh", "-c", "python -m app.migrate && uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
