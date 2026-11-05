
# ---------- web ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

# ---------- runtime ----------
FROM python:3.12-slim AS runtime

# 默认不装 gcc/bubblewrap：代码沙箱默认关闭，需要时 --build-arg INSTALL_SANDBOX=1
ARG INSTALL_SANDBOX=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KAODIAN_CONTENT_DIR=/content \
    KAODIAN_DATA_DIR=/data \
    TZ=Asia/Shanghai

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && if [ "$INSTALL_SANDBOX" = "1" ]; then \
         apt-get install -y --no-install-recommends gcc libc6-dev bubblewrap; \
       fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/requirements.txt apps/api/constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

COPY --chown=1000:1000 apps/api/app ./apps/api/app
COPY --chown=1000:1000 apps/cli ./apps/cli
COPY --chown=1000:1000 bin ./bin
COPY --chown=1000:1000 config ./config
COPY --chown=1000:1000 starter-content ./starter-content
COPY --chown=1000:1000 examples ./examples
COPY --chown=1000:1000 --from=web /web/dist ./apps/web/dist

RUN groupadd -g 1000 kaodian 2>/dev/null || true \
    && useradd -u 1000 -g 1000 -M -s /usr/sbin/nologin kaodian 2>/dev/null || true \
    && mkdir -p /data /content && chown 1000:1000 /data

USER 1000:1000
VOLUME ["/data"]
# /content 由宿主机内容仓库只读挂载；未挂载时可用 /app/starter-content
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"

CMD ["uvicorn", "app.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
