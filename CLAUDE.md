# CLAUDE.md - Developer Context & Setup

Quick reference for the Consorcio Canalero platform rewrite.

## Project Overview

**Consorcio Canalero 10 de Mayo** - Sistema integral de gestion para consorcios canaleros. Self-hosted, clone-and-deploy ready.

### Stack

- **Frontend**: React 19, TypeScript, Vite, Mantine UI, Leaflet (`consorcio-web/`)
- **Backend**: FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic, fastapi-users (`gee-backend/`)
- **Database**: PostgreSQL + PostGIS (direct, no Supabase dependency)
- **Auth**: JWT (fastapi-users) + optional Google OAuth
- **Geo**: Google Earth Engine integration, GDAL-based geo worker
- **Testing**: Pytest (backend), Vitest (frontend)
- **CI/CD**: GitHub Actions, Docker Compose

### Directory Structure

```
consorcio-canalero/
├── consorcio-web/              # React frontend (Vite)
├── gee-backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/v2/             # V2 API router aggregator
│   │   ├── auth/               # fastapi-users auth (JWT + OAuth)
│   │   ├── db/                 # Base, session, migrations
│   │   │   └── migrations/     # Alembic migrations
│   │   ├── domains/            # Screaming Architecture domains
│   │   │   ├── capas/          # Map layers management
│   │   │   ├── denuncias/      # Citizen reports
│   │   │   ├── finanzas/       # Finance (ingresos, gastos, presupuestos)
│   │   │   ├── geo/            # Geo processing + GEE + intelligence
│   │   │   │   └── hydrology/  # Flood flow estimation (Kirpich + Método Racional)
│   │   │   ├── infraestructura/# Assets + maintenance logs
│   │   │   ├── monitoring/     # Sugerencias + GEE analysis tracking
│   │   │   ├── padron/         # Consorcista registry
│   │   │   ├── settings/       # System settings (per-deployment config)
│   │   │   └── tramites/       # Procedures + tracking
│   │   ├── core/               # Logging, exceptions, rate limiting
│   │   └── shared/             # Cross-domain utilities
│   ├── tests/new/              # Tests for new architecture
│   └── alembic.ini
├── setup.sh                    # Clone-and-deploy setup script
├── docker-compose.yml
├── openspec/                   # SDD specs
└── docs/
```

### Domain Architecture (Screaming Architecture)

Each domain under `gee-backend/app/domains/` follows the same pattern:

```
domain/
├── models.py       # SQLAlchemy 2.0 models (Mapped, mapped_column)
├── schemas.py      # Pydantic v2 schemas (request/response)
├── repository.py   # Data access layer (SELECT/INSERT/UPDATE only)
├── service.py      # Business logic (orchestrates repository + rules)
└── router.py       # FastAPI router (HTTP layer, dependencies)
```

Base classes: `UUIDMixin`, `TimestampMixin`, `Base` from `app.db.base`.

**Geo subdomain — hydrology/**
Nested under `geo/`, the `hydrology/` subdomain handles quantitative peak flow
estimation (Kirpich + Método Racional) for storm event dates. Distinct from:
- `geo/hydrology.py` (TWI — static terrain property, no storm modelling)
- `ml/flood_prediction.py` (U-Net pixel-level flood detection post-event)

---

## Quick Setup

```bash
# Clone and run
git clone <repo-url> && cd consorcio-canalero
./setup.sh

# Or manual:
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env  # Edit with real values
```

### Key Commands

**Backend**:
```bash
cd gee-backend
source venv/bin/activate

# Dev server
uvicorn app.main:app --reload

# Tests
pytest tests/new/ -v                    # New architecture tests
pytest tests/new/ -v --cov=app          # With coverage

# Database
alembic upgrade head                    # Run migrations
alembic revision --autogenerate -m "description"  # New migration

# Lint
ruff check . && ruff format --check .
```

**Frontend**:
```bash
cd consorcio-web
npm install && npm run dev              # Dev server
npm run test                            # Unit tests
npm run build                           # Production build
```

**Docker**:
```bash
docker compose up -d                    # All services
docker compose up -d postgres redis     # Just DB + cache
docker compose logs -f backend          # Follow logs
```

---

## API

All new endpoints are under `/api/v2`. Key route groups:

| Prefix | Domain | Auth |
|--------|--------|------|
| `/api/v2/auth/*` | Login, register, user mgmt | Varies |
| `/api/v2/padron/*` | Consorcista registry | Operator+ |
| `/api/v2/denuncias/*` | Citizen reports | Operator+ |
| `/api/v2/finanzas/*` | Finance management | Operator+ |
| `/api/v2/infraestructura/*` | Assets + maintenance | Operator+ |
| `/api/v2/tramites/*` | Procedures | Operator+ |
| `/api/v2/capas/*` | Map layers | Operator+ |
| `/api/v2/geo/*` | Geo processing + GEE | Operator+ |
| `/api/v2/monitoring/*` | Sugerencias + analysis | Varies |
| `/api/v2/settings/*` | System settings | Operator+ (read), Admin (write) |
| `/api/v2/public/*` | Public viewer, branding | No auth |
| `/api/v2/admin/publish/*` | Layer publication | Admin |

### System Settings

Per-deployment configuration stored in `system_settings` table. Categories: `general`, `branding`, `territorio`, `analisis`, `contacto`.

Public branding endpoint (no auth): `GET /api/v2/public/settings/branding`

Seed defaults: `SettingsService.seed_defaults(db)` or via `setup.sh`.

---

## Auth Model

Three roles: `admin`, `operador`, `ciudadano`.

- `require_admin` — admin only
- `require_admin_or_operator` — admin + operador
- `require_authenticated` — any logged-in user

Auth dependencies use lazy imports to avoid circular deps.

---

## Environment Variables

See `gee-backend/.env.example` for full reference. Key vars:

```env
DATABASE_URL=postgresql://consorcio:consorcio_dev@localhost:5432/consorcio
JWT_SECRET=<openssl rand -hex 32>
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
# Legacy Supabase vars still required during migration
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=dummy-key
```

Frontend: `consorcio-web/.env.example` — just `VITE_API_URL`.

---

## Testing

Tests for the new architecture live in `gee-backend/tests/new/`.

Fixtures in `conftest.py`:
- `db` — per-test session with rollback (real PostgreSQL)
- `db_session_factory` — session factory for DI override
- `test_engine` — session-scoped engine + table creation

Pattern: real database, transaction-per-test, no mocking for data access.

---

## Conventions

- **Commits**: Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`)
- **Models**: UUID primary keys, timestamps on all tables
- **Schemas**: Pydantic v2, `model_config = ConfigDict(from_attributes=True)`
- **Repositories**: Stateless classes, receive `db: Session` as first arg
- **Services**: Orchestrate repos, raise `HTTPException` for business errors
- **Routers**: Thin HTTP layer, delegate to services

---

Last updated: 2026-04-05
Maintained by: @javier
