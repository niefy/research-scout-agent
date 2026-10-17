PYTHON ?= python3
VENV ?= .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help install dev-backend dev-frontend test lint build seed seed-demo crawl up down logs ps

help:
	@echo "Research Scout"
	@echo ""
	@echo "  make install       Create .venv, install backend + frontend dependencies"
	@echo "  make dev-backend   Run FastAPI on :8000 (reload)"
	@echo "  make dev-frontend  Run Vite on :5173 (proxies /api to :8000)"
	@echo "  make test          Run backend tests"
	@echo "  make lint          Ruff + vue-tsc"
	@echo "  make build         Build the frontend bundle"
	@echo "  make seed          Seed channels, industries and A-share securities"
	@echo "  make seed-demo     Seed demo users, authors, reports and watchlists"
	@echo "  make crawl         Crawl mock sources and run analysis"
	@echo "  make up            Start the full Docker stack on :8080"
	@echo "  make down          Stop the Docker stack"
	@echo "  make logs          Follow Docker logs"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e "./backend[dev]"
	cd frontend && npm install

dev-backend:
	cd backend && ../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && ../$(VENV)/bin/pytest -q

lint:
	cd backend && ../$(VENV)/bin/ruff check app tests
	cd frontend && npm run typecheck

build:
	cd frontend && npm run build

seed:
	cd backend && ../$(VENV)/bin/python -m app.cli seed

seed-demo:
	cd backend && ../$(VENV)/bin/python -m app.cli seed-demo

crawl:
	cd backend && ../$(VENV)/bin/python -m app.cli crawl --channels mock --limit 10 --analyze

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ps:
	docker compose ps
