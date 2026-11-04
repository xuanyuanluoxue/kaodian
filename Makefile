PY := .venv/bin/python

.PHONY: setup dev-api dev-web build test docker

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r apps/api/requirements-dev.txt
	.venv/bin/pip install -r apps/mcp/requirements.txt
	cd apps/web && npm install

dev-api:
	cd apps/api && ../../.venv/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd apps/web && npm run dev

build:
	cd apps/web && npm run build

test:
	$(PY) -m pytest apps/api/tests -q

docker:
	docker compose up --build