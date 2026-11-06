FROM node:24-bookworm-slim AS web
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY index.html tsconfig.json vite.config.ts ./
COPY frontend ./frontend
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY --from=web /src/dist ./dist
COPY backend ./backend
COPY scripts/manage.py scripts/check_model.py ./scripts/
USER appuser
ENV APP_DB=/data/family.sqlite3 COOKIE_SECURE=true DEMO_MODE=false
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
