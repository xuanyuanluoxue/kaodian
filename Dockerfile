# ---------- web ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com
COPY apps/web/ ./
RUN npm run build

# ---------- api ----------
FROM python:3.12-slim AS api
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KAODIAN_DB=/data/kaodian.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev bubblewrap \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY apps/api/app ./apps/api/app
COPY config ./config
COPY --from=web /web/dist ./apps/web/dist

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]