# ==============================================
# Consorcio Canalero - Project Makefile
# ==============================================

.PHONY: help install dev build test lint clean docker-up docker-down migrate setup \
        backend-install frontend-install backend-dev frontend-dev backend-test \
        frontend-test backend-lint frontend-lint docker-build docker-logs \
        docker-restart docker-clean format security-scan db-upgrade db-downgrade \
        ci-quick ci-full install-hooks rag-db test-rag test-rag-corpus

# Default target
.DEFAULT_GOAL := help

# Colors for terminal output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Project paths
PROJECT_ROOT := $(shell pwd)
BACKEND_DIR := $(PROJECT_ROOT)/gee-backend
FRONTEND_DIR := $(PROJECT_ROOT)/consorcio-web

# Docker compose command
DOCKER_COMPOSE := docker compose

# ==============================================
# HELP
# ==============================================
help: ## Show this help message
	@echo ""
	@echo "$(BLUE)Consorcio Canalero - Available Commands$(NC)"
	@echo "=========================================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ==============================================
# CI-LOCAL (run before push to save GitHub Actions minutes)
# ==============================================
ci-quick: ## Run quick CI checks locally (lint + type-check)
	@bash ./.ci-local/ci-local.sh quick

ci-full: ## Run full CI checks locally (lint + type-check + test + build)
	@bash ./.ci-local/ci-local.sh full

install-hooks: ## Install git hooks for pre-push validation
	@echo "$(BLUE)Installing git hooks...$(NC)"
	@cp .ci-local/hooks/pre-push .git/hooks/pre-push
	@chmod +x .git/hooks/pre-push
	@chmod +x .ci-local/ci-local.sh
	@echo "$(GREEN)Git hooks installed! Pre-push will run ci-local quick.$(NC)"

# ==============================================
# SETUP & INSTALL
# ==============================================
setup: ## Initial project setup (install all dependencies + create env files)
	@echo "$(BLUE)Setting up project...$(NC)"
	@$(MAKE) install
	@if [ ! -f $(BACKEND_DIR)/.env ]; then \
		cp $(BACKEND_DIR)/.env.example $(BACKEND_DIR)/.env; \
		echo "$(YELLOW)Created backend .env from example$(NC)"; \
	fi
	@if [ ! -f $(FRONTEND_DIR)/.env ]; then \
		cp $(FRONTEND_DIR)/.env.example $(FRONTEND_DIR)/.env; \
		echo "$(YELLOW)Created frontend .env from example$(NC)"; \
	fi
	@echo "$(GREEN)Setup complete!$(NC)"

install: backend-install frontend-install ## Install all dependencies (backend + frontend)
	@echo "$(GREEN)All dependencies installed!$(NC)"

backend-install: ## Install backend Python dependencies
	@echo "$(BLUE)Installing backend dependencies...$(NC)"
	cd $(BACKEND_DIR) && \
		python -m pip install --upgrade pip && \
		pip install --require-hashes -r requirements-dev.lock && \
		pip install ruff mypy pytest pytest-cov pytest-asyncio httpx bandit
	@echo "$(GREEN)Backend dependencies installed!$(NC)"

frontend-install: ## Install frontend npm dependencies
	@echo "$(BLUE)Installing frontend dependencies...$(NC)"
	cd $(FRONTEND_DIR) && npm ci --no-audit --no-fund --legacy-peer-deps
	@echo "$(GREEN)Frontend dependencies installed!$(NC)"

# ==============================================
# DEVELOPMENT
# ==============================================
dev: ## Start development servers (backend + frontend in parallel)
	@echo "$(BLUE)Starting development servers...$(NC)"
	@$(MAKE) -j2 backend-dev frontend-dev

backend-dev: ## Start backend development server with hot reload
	@echo "$(BLUE)Starting backend server...$(NC)"
	cd $(BACKEND_DIR) && \
		uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend-dev: ## Start frontend development server
	@echo "$(BLUE)Starting frontend server...$(NC)"
	cd $(FRONTEND_DIR) && npm run dev

# ==============================================
# BUILD
# ==============================================
build: backend-build frontend-build ## Build all projects
	@echo "$(GREEN)All builds complete!$(NC)"

backend-build: ## Build backend Docker image
	@echo "$(BLUE)Building backend Docker image...$(NC)"
	cd $(BACKEND_DIR) && \
		docker build -t consorcio-backend:latest --target production .
	@echo "$(GREEN)Backend image built!$(NC)"

frontend-build: ## Build frontend for production
	@echo "$(BLUE)Building frontend...$(NC)"
	cd $(FRONTEND_DIR) && npm run build
	@echo "$(GREEN)Frontend built!$(NC)"

# ==============================================
# TESTING
# ==============================================
test: backend-test frontend-test ## Run all tests
	@echo "$(GREEN)All tests complete!$(NC)"

backend-test: ## Run backend tests with coverage
	@echo "$(BLUE)Running backend tests...$(NC)"
	cd $(BACKEND_DIR) && \
		pytest tests/new/ -v \
			--cov=app \
			--cov-report=term-missing \
			--cov-report=html:coverage_html \
			--cov-fail-under=70
	@echo "$(GREEN)Backend tests complete!$(NC)"

frontend-test: ## Run frontend tests
	@echo "$(BLUE)Running frontend tests...$(NC)"
	cd $(FRONTEND_DIR) && npm run test 2>/dev/null || echo "$(YELLOW)No frontend tests configured$(NC)"

# ==============================================
# LINTING & FORMATTING
# ==============================================
lint: backend-lint frontend-lint ## Run all linters
	@echo "$(GREEN)Linting complete!$(NC)"

backend-lint: ## Lint backend with Ruff and MyPy
	@echo "$(BLUE)Linting backend...$(NC)"
	cd $(BACKEND_DIR) && \
		ruff check app/ --fix && \
		ruff format app/ && \
		mypy app/ --ignore-missing-imports
	@echo "$(GREEN)Backend linting complete!$(NC)"

frontend-lint: ## Lint frontend with Biome
	@echo "$(BLUE)Linting frontend...$(NC)"
	cd $(FRONTEND_DIR) && npm run lint:fix && npm run format
	@echo "$(GREEN)Frontend linting complete!$(NC)"

format: ## Format all code
	@echo "$(BLUE)Formatting code...$(NC)"
	cd $(BACKEND_DIR) && ruff format app/
	cd $(FRONTEND_DIR) && npm run format
	@echo "$(GREEN)Formatting complete!$(NC)"

security-scan: ## Run security scans (Bandit for Python)
	@echo "$(BLUE)Running security scans...$(NC)"
	cd $(BACKEND_DIR) && bandit -r app/ -f txt
	@echo "$(GREEN)Security scan complete!$(NC)"

# ==============================================
# DOCKER OPERATIONS
# ==============================================
docker-up: ## Start all Docker services
	@echo "$(BLUE)Starting Docker services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)Services started!$(NC)"
	@echo ""
	@echo "$(BLUE)Services:$(NC)"
	@echo "  Backend:  http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"
	@echo "  Redis:    localhost:6379"

docker-down: ## Stop all Docker services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)Services stopped!$(NC)"

docker-build: ## Build all Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	$(DOCKER_COMPOSE) build --no-cache
	@echo "$(GREEN)Docker images built!$(NC)"

docker-logs: ## Show Docker logs (follow mode)
	$(DOCKER_COMPOSE) logs -f

docker-restart: docker-down docker-up ## Restart all Docker services

docker-clean: ## Remove all Docker containers, images, and volumes
	@echo "$(YELLOW)Warning: This will remove all project containers, images, and volumes!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && \
		[ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ] && \
		$(DOCKER_COMPOSE) down -v --rmi all --remove-orphans || \
		echo "$(BLUE)Cancelled$(NC)"

docker-monitoring: ## Start services with monitoring (Flower)
	@echo "$(BLUE)Starting services with monitoring...$(NC)"
	$(DOCKER_COMPOSE) --profile monitoring up -d
	@echo "$(GREEN)Services started with monitoring!$(NC)"
	@echo "  Flower: http://localhost:5555"

docker-scheduler: ## Start services with Celery Beat scheduler
	@echo "$(BLUE)Starting services with scheduler...$(NC)"
	$(DOCKER_COMPOSE) --profile with-scheduler up -d
	@echo "$(GREEN)Services started with scheduler!$(NC)"

# ==============================================
# DATABASE & MIGRATIONS
# ==============================================
migrate: db-upgrade ## Run database migrations (alias for db-upgrade)

db-upgrade: ## Apply database migrations
	@echo "$(BLUE)Running database migrations...$(NC)"
	cd $(BACKEND_DIR) && \
		alembic upgrade head 2>/dev/null || \
		echo "$(YELLOW)Alembic not configured or no migrations to run$(NC)"

db-downgrade: ## Rollback last database migration
	@echo "$(BLUE)Rolling back last migration...$(NC)"
	cd $(BACKEND_DIR) && \
		alembic downgrade -1 2>/dev/null || \
		echo "$(YELLOW)Alembic not configured$(NC)"

db-revision: ## Create a new migration revision
	@read -p "Migration message: " msg && \
		cd $(BACKEND_DIR) && \
		alembic revision --autogenerate -m "$$msg"

# ==============================================
# CLEANUP
# ==============================================
clean: ## Clean build artifacts and caches
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	# Python cleanup
	find $(BACKEND_DIR) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find $(BACKEND_DIR) -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/coverage_html $(BACKEND_DIR)/.coverage $(BACKEND_DIR)/coverage.xml 2>/dev/null || true
	# Frontend cleanup
	rm -rf $(FRONTEND_DIR)/dist $(FRONTEND_DIR)/.astro 2>/dev/null || true
	rm -rf $(FRONTEND_DIR)/node_modules/.cache 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete!$(NC)"

clean-all: clean ## Deep clean including node_modules and virtual environments
	@echo "$(YELLOW)Performing deep clean...$(NC)"
	rm -rf $(FRONTEND_DIR)/node_modules 2>/dev/null || true
	rm -rf $(BACKEND_DIR)/.venv $(BACKEND_DIR)/venv 2>/dev/null || true
	@echo "$(GREEN)Deep cleanup complete!$(NC)"

# ==============================================
# RAG (pgvector, dev-only — see openspec/changes/consorcio-rag/design.md D7)
# ==============================================
rag-db: ## Build + start the pgvector-enabled Postgres service (opt-in, dev only)
	@echo "$(BLUE)Building consorcio-postgres:16-vector...$(NC)"
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.pgvector.yml build postgres
	@echo "$(BLUE)Starting consorcio-postgres:16-vector...$(NC)"
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.pgvector.yml up -d postgres
	@echo "$(GREEN)consorcio-postgres:16-vector is up.$(NC)"
	@echo "$(YELLOW)Antes de volver a la imagen sin vector: alembic downgrade (primero), si no el volumen compartido queda ilegible.$(NC)"

test-rag: ## Run the pgvector-marked test suite against consorcio-postgres:16-vector
	@echo "$(BLUE)Building consorcio-postgres:16-vector...$(NC)"
	docker build -f docker/postgres/Dockerfile -t consorcio-postgres:16-vector docker/postgres
	@echo "$(BLUE)Running pgvector-marked tests...$(NC)"
# `TEST_DATABASE_URL=` is load-bearing, not tidiness. conftest's
# `_resolve_database_url()` honors TEST_DATABASE_URL BEFORE testcontainers, so a
# developer with that variable exported would run this target against their own
# database while the success message still claims "ran for real against
# consorcio-postgres:16-vector" — the image would be built and never touched.
# Clearing it here makes image selection the only possible DB path (ledger
# RAG1-001).
	@cd $(BACKEND_DIR) && \
		TEST_DATABASE_URL= \
		TEST_POSTGRES_IMAGE=consorcio-postgres:16-vector \
		venv/bin/pytest -m pgvector --junitxml=rag-junit.xml tests/new/; \
		pytest_status=$$?; \
		if [ $$pytest_status -eq 5 ]; then \
			echo "$(RED)test-rag: exit code 5 — zero pgvector tests were collected. Check the marker and -m expression.$(NC)"; \
			exit 1; \
		elif [ $$pytest_status -ne 0 ]; then \
			echo "$(RED)test-rag: pytest failed (exit $$pytest_status).$(NC)"; \
			exit $$pytest_status; \
		fi; \
		skipped=$$(venv/bin/python -c "import xml.etree.ElementTree as ET; root = ET.parse('rag-junit.xml').getroot(); suites = root.findall('testsuite') if root.tag == 'testsuites' else [root]; print(sum(int(s.attrib.get('skipped', 0)) for s in suites))"); \
		if [ "$$skipped" != "0" ]; then \
			echo "$(RED)test-rag: $$skipped pgvector test(s) skipped despite the vector image — the image is silently degraded (exit code 5 alone cannot catch this; see design.md D7).$(NC)"; \
			exit 1; \
		fi; \
		echo "$(GREEN)test-rag: all pgvector tests ran for real against consorcio-postgres:16-vector, zero skipped.$(NC)"

test-rag-corpus: ## Run the RAG corpus-contract tests against the real SHA-pinned checkout (LOCAL ONLY — CI cannot hold the private corpus)
# CI covers the STRUCTURAL tests only. Every content assertion — the 35-document
# check, the 1383/65 counts, the vigencia canary, verbatim fidelity, determinism,
# pruning, idempotency — hides behind RAG_CORPUS_PATH, which CI never sets
# because the corpus repository is private and V0 is all-local by owner rule.
# Those tests therefore report SKIPPED and the CI run is green (ledger RAG2-005).
# This target is where that contract actually gets exercised, and like `test-rag`
# it treats a SKIP as a failure: "the corpus suite passed" must never be able to
# mean "the corpus suite did not run".
	@if [ -z "$$RAG_CORPUS_PATH" ]; then \
		echo "$(RED)test-rag-corpus: RAG_CORPUS_PATH is not set. Point it at a checkout of consorcio-corpus-legal at the pinned SHA, e.g.$(NC)"; \
		echo "$(YELLOW)  make test-rag-corpus RAG_CORPUS_PATH=~/path/to/consorcio-corpus-legal$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Running RAG corpus-contract tests against $$RAG_CORPUS_PATH...$(NC)"
	@cd $(BACKEND_DIR) && \
		RAG_CORPUS_PATH=$$RAG_CORPUS_PATH \
		venv/bin/pytest -m corpus --junitxml=rag-corpus-junit.xml tests/new/conocimiento/; \
		pytest_status=$$?; \
		if [ $$pytest_status -eq 5 ]; then \
			echo "$(RED)test-rag-corpus: exit code 5 — zero corpus tests were collected. Check the `corpus` marker and the -m expression.$(NC)"; \
			exit 1; \
		elif [ $$pytest_status -ne 0 ]; then \
			echo "$(RED)test-rag-corpus: pytest failed (exit $$pytest_status).$(NC)"; \
			exit $$pytest_status; \
		fi; \
		skipped=$$(venv/bin/python -c "import xml.etree.ElementTree as ET; root = ET.parse('rag-corpus-junit.xml').getroot(); suites = root.findall('testsuite') if root.tag == 'testsuites' else [root]; print(sum(int(s.attrib.get('skipped', 0)) for s in suites))"); \
		if [ "$$skipped" != "0" ]; then \
			echo "$(RED)test-rag-corpus: $$skipped corpus test(s) skipped despite RAG_CORPUS_PATH being set — the checkout is wrong or degraded, and a green run would have covered nothing.$(NC)"; \
			exit 1; \
		fi; \
		echo "$(GREEN)test-rag-corpus: the whole corpus contract ran for real against the pinned checkout, zero skipped.$(NC)"

# ==============================================
# UTILITY COMMANDS
# ==============================================
shell-backend: ## Open Python shell in backend context
	cd $(BACKEND_DIR) && python -i -c "from app.main import app; print('App loaded')"

shell-docker: ## Open shell in backend Docker container
	$(DOCKER_COMPOSE) exec backend /bin/bash

redis-cli: ## Open Redis CLI
	$(DOCKER_COMPOSE) exec redis redis-cli

check-env: ## Check if all required environment variables are set
	@echo "$(BLUE)Checking environment files...$(NC)"
	@if [ -f $(BACKEND_DIR)/.env ]; then \
		echo "$(GREEN)Backend .env exists$(NC)"; \
	else \
		echo "$(RED)Backend .env missing!$(NC)"; \
	fi
	@if [ -f $(FRONTEND_DIR)/.env ]; then \
		echo "$(GREEN)Frontend .env exists$(NC)"; \
	else \
		echo "$(RED)Frontend .env missing!$(NC)"; \
	fi

status: ## Show status of all services
	@echo "$(BLUE)Docker Services Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(BLUE)Backend Health:$(NC)"
	@curl -s http://localhost:8000/health 2>/dev/null && echo "" || echo "$(RED)Backend not running$(NC)"
	@echo ""
	@echo "$(BLUE)Frontend Status:$(NC)"
	@curl -s -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null || echo "$(RED)Frontend not running$(NC)"
