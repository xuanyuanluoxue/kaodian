PY := .venv/bin/python
PIP := .venv/bin/pip
CONSTRAINTS := apps/api/constraints.txt

.PHONY: setup dev-api dev-web build test lint check docker docker-sandbox

setup:
	python3 -m venv .venv
	$(PIP) install -r apps/api/requirements-dev.txt -c $(CONSTRAINTS)
	$(PIP) install -r apps/mcp/requirements.txt -c $(CONSTRAINTS)
	cd apps/web && npm ci

dev-api:
	cd apps/api && ../../.venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd apps/web && npm run dev

build:
	cd apps/web && npm run build

test:
	$(PY) -m pytest

lint:
	cd apps/web && npm run lint

check: test lint build

docker:
	KAODIAN_UID=$$(id -u) KAODIAN_GID=$$(id -g) docker compose up --build

docker-sandbox:
	KAODIAN_UID=$$(id -u) KAODIAN_GID=$$(id -g) INSTALL_SANDBOX=1 KAODIAN_ALLOW_CODE_RUN=1 docker compose up --build
