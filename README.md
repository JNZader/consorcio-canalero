# Consorcio Canalero 10 de Mayo

GIS-powered platform for canal consortium operations, hydrologic monitoring, and public reporting.

[![Live Demo](https://img.shields.io/badge/demo-live-success?style=flat-square)](https://consorcio-canalero.pages.dev)
[![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20Celery-blue?style=flat-square)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb?style=flat-square)](https://react.dev/)
[![Database](https://img.shields.io/badge/db-PostgreSQL%20%2B%20PostGIS-336791?style=flat-square)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

Demo: [consorcio-canalero.pages.dev](https://consorcio-canalero.pages.dev)

Visuals coming soon. The strongest differentiator in this project is the GIS workflow: public reports, operator workflows, and hydrologic intelligence all connect back to the same map and territorial data model.

## Quick Portfolio Snapshot

- Built for a real canal consortium in Marcos Juárez, Cordoba, Argentina.
- Combines administrative management with geospatial intelligence instead of treating GIS as an isolated viewer.
- Covers padrón, denuncias, tramites, finanzas, reuniones, capas, monitoring, settings, and geo in one deployable system.
- Uses PostGIS, Google Earth Engine, Martin/PMTiles, and background workers for terrain, imagery, and risk analysis.
- Self-hosted architecture with split frontend/backend deployment: Cloudflare Pages for web, Hetzner-hosted services for API, tiles, jobs, and data.

## Why It Matters

Typical municipal or consortium software handles paperwork but ignores territory. Typical GIS demos look impressive but stop short of daily operations.

This platform connects both sides:

- A citizen can submit a denuncia with photos and map location.
- An operator can triage it, relate it to zones, roads, canals, or risk layers, and track the response.
- The consortium can manage members, finances, procedures, meetings, and public branding from the same system.
- Technical users can run flood, terrain, and hydrologic analysis on the same geospatial base used by operations.

Use cases:

- Water drainage and canal maintenance planning.
- Flood-risk monitoring with Sentinel-1 SAR and DEM-derived terrain products.
- Public intake for reports and suggestions without requiring login.
- Administrative coordination across registry, finances, procedures, and meetings.
- GIS data export for field teams, QGIS users, and Google Earth consumers.

## Quick Start

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh
```

Manual startup:

```bash
# Backend
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (new terminal)
cd consorcio-web
npm install
cp .env.example .env
npm run dev
```

Docker:

```bash
docker compose up -d
```

## Jump To Technical Docs

- [Technical README](#technical-readme)
- [Architecture](#architecture)
- [Functional Domains](#functional-domains)
- [Geospatial Capabilities](#geospatial-capabilities)
- [Auth And Roles](#auth-and-roles)
- [Background Jobs](#background-jobs)
- [Export And Reporting](#export-and-reporting)
- [Testing](#testing)
- [Deployment](#deployment)

---

## Technical README

## Table of Contents

- [System Overview](#system-overview)
- [Stack](#stack)
- [Architecture](#architecture)
- [Functional Domains](#functional-domains)
- [Geospatial Capabilities](#geospatial-capabilities)
- [Auth and Roles](#auth-and-roles)
- [Background Jobs](#background-jobs)
- [Export and Reporting](#export-and-reporting)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Quick Start](#quick-start-1)
- [API Surface](#api-surface)
- [Testing](#testing)
- [Deployment](#deployment)
- [CI/CD Notes](#cicd-notes)
- [License](#license)

## System Overview

Consorcio Canalero 10 de Mayo is a self-hosted operational platform for water-management organizations. It combines administrative workflows, citizen participation, and hydrologic/geospatial analysis in one system.

The platform covers four broad areas:

1. Administrative operations: padrón, finanzas, tramites, reuniones, and settings.
2. Public participation: denuncias, sugerencias, public branding, and public map access.
3. Geospatial intelligence: interactive map layers, Earth Engine imagery, terrain-derived analysis, HCI scoring, and conflict detection.
4. Operational deployment: clone-and-deploy setup, containerized services, and split frontend/backend hosting.

## Stack

| Layer | Technologies |
|-------|--------------|
| Backend | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Frontend | React 19, TypeScript, Vite 7, Mantine v8, TanStack Router, TanStack Query, Zustand |
| Database | PostgreSQL, PostGIS, GeoAlchemy2 |
| GIS and imagery | Google Earth Engine, Rasterio, GDAL, WhiteboxTools, Shapely |
| Vector tiles and maps | MapLibre GL, PMTiles, Martin tile server |
| Background processing | Celery, Redis |
| Reporting | ReportLab, QGIS project export, KMZ export |
| Testing | Pytest, Vitest, Playwright, Stryker |
| Tooling | Ruff, Biome, Docker Compose, GitHub Actions |
| Hosting | Cloudflare Pages, Hetzner, GHCR |

## Architecture

The backend follows **Screaming Architecture**. The repository structure prioritizes business capabilities over technical layers, so the codebase tells you what the system does: `padron`, `denuncias`, `tramites`, `finanzas`, `reuniones`, `capas`, `monitoring`, `settings`, `geo`.

Each domain under `gee-backend/app/domains/` owns its internal slice:

```text
domain/
|- models.py       # SQLAlchemy models
|- schemas.py      # Pydantic request/response models
|- repository.py   # Data access only
|- service.py      # Business rules and orchestration
`- router.py       # FastAPI HTTP layer
```

Why this matters:

- Business rules stay close to their domain instead of being scattered across generic folders.
- Each domain can evolve with clearer boundaries.
- API routing stays thin, repositories stay focused on persistence, and services hold the use-case logic.
- The geo domain can grow into specialized submodules without dragging the rest of the codebase into GIS complexity.

Base conventions:

- UUID primary keys and timestamps across tables.
- Pydantic v2 schemas with ORM-friendly serialization.
- Stateless repositories receiving `db: Session`.
- Thin routers delegating to services.
- Shared infrastructure in `app/core/`, `app/db/`, and `app/shared/`.

## Functional Domains

### `padron`

Master registry for consorcistas, including CUIT, fractions, water rights, quotas, category, and account status.

- Full CRUD for member records.
- Bulk CSV/XLSX import with validation.
- Aggregated metrics such as total members, debt, and category distribution.

### `denuncias`

Public-facing citizen reports with operational follow-up.

- No-login report submission.
- Photo upload and map-based geolocation.
- Workflow states: open, in progress, resolved, rejected.
- Audit history for operator actions.
- Filters and response metrics.

### `tramites`

Administrative proceedings and internal case tracking.

- Type, priority, and state management.
- Chronological follow-up comments.
- Full expediente export to PDF.

### `finanzas`

Annual financial management for the consortium.

- Income tracking by category.
- Expense tracking by budget line.
- Annual budget definitions.
- Execution analysis: planned vs. actual.
- Annual financial summary export to PDF.

### `reuniones`

Meeting and agenda management.

- Meeting calendar by type.
- Collaborative agenda construction.
- Automatic linkage of citizen suggestions to the next meeting.
- Agenda/order-of-the-day PDF export.

### `capas`

Map-layer management.

- CRUD for raster and vector layers.
- Public vs operator-only visibility.
- Ordering and publication behavior for the viewer.
- Sources can come from GEE, static files, or PostGIS-backed data.

### `monitoring`

Cross-cutting monitoring and participation workflows.

- Public suggestions.
- Dashboard KPIs spanning denuncias, tramites, and finanzas.
- Persistent tracking of executed GEE analyses.

### `settings`

Per-deployment system configuration.

- General, branding, territory, analysis, and contact settings.
- Public branding endpoint so the frontend can load logo and colors without auth.
- Selected satellite-image persistence and before/after comparison support.
- Configurable analysis weights and thresholds.

### `geo`

The most specialized domain, handling spatial processing, imagery, terrain analysis, and intelligence.

Sub-areas include:

- Core geo bundles and territorial hierarchy.
- GEE-backed imagery and layer catalog.
- Analysis jobs with asynchronous execution state.
- Intelligence endpoints for HCI, conflicts, zonification, alerts, and composite analysis.
- Visualization/export support including QGIS project generation and terrain outputs.

## Geospatial Capabilities

### Vector layers

- Watersheds.
- Surveyed and proposed canals.
- Rural roads with service-state visualization.
- Rural schools.
- Pilar Verde and related agroforestry layers.
- Operational zones, conflict areas, and alerts.
- Cadastral and support datasets.

### Raster and DEM-derived products

- SRTM DEM.
- HAND.
- Slope.
- Flow accumulation.
- TWI.
- Hillshade.
- Sentinel-2 NDVI and related water/vegetation products.
- Sentinel-1 SAR imagery for cloud-independent flood analysis.

### Analysis capabilities

- SAR flood detection through before/after comparison.
- Hydrologic modeling with Kirpich concentration time and Rational Method peak flow.
- HCI (Hydric Criticality Index) by zone.
- Conflict detection through geometric overlap across infrastructure and risk layers.
- Automated zonification.
- Composite flood-risk and drainage-need analysis.
- 3D terrain rendering and fly-over export.

### Google Earth Engine integration

- Collections used include `COPERNICUS/S2`, `COPERNICUS/S1_GRD`, and `USGS/SRTM/90_V4`.
- The system exposes processed layers, imagery dates, and analysis results back to the web app.
- Martin and PMTiles support efficient map delivery for heavier vector data.

## Auth and Roles

Role model:

| Role | Access |
|------|--------|
| `admin` | Full access, settings write access, invitations, admin workflows |
| `operador` | CRUD on operational domains, read access to settings |
| `ciudadano` | Public reports and suggestions; most public flows do not require authentication |

Auth mechanisms:

- JWT via `fastapi-users` bearer tokens. The current frontend adapter stores the
  session in `sessionStorage` and sends `Authorization: Bearer ...` to `/api/v2/*`.
- Optional Google OAuth.
- Invitation-based operator onboarding with activation tokens.
- FastAPI dependencies such as `require_admin`, `require_admin_or_operator`, and authenticated-user guards.

## Background Jobs

Asynchronous processing runs through Celery with Redis as broker/cache support. Heavy geo or export workflows are intentionally kept out of the request/response path.

Important jobs documented in the codebase and existing docs:

| Task | Purpose |
|------|---------|
| `task_dem_pipeline_full` | DEM to HAND, slope, and TWI pipeline |
| `task_export_geo_bundle` | Package geospatial layers for download |
| `task_generate_zonification` | Generate operational zoning from DEM thresholds |
| `task_calculate_hci_all_zones` | Batch HCI calculation across zones |
| `task_detect_all_conflicts` | Batch geospatial conflict detection |
| `task_composite_analysis_task` | Composite flood-risk and drainage-need analysis |

Operational behavior:

- Job state is persisted in the database.
- The frontend polls analysis/job endpoints to show progress.
- Worker services run separately from the main API container.

## Export and Reporting

### PDF reporting

The platform generates branded PDFs for operational and administrative workflows.

- Tramite records with chronological tracking.
- Meeting agendas/order-of-the-day documents.
- Annual financial summaries.
- Additional technical or asset-style sheets depending on workflow.

### Geospatial export

- KMZ export for Google Earth.
- Automatic PII stripping for sensitive data before KMZ generation.
- GeoJSON and CSV exports for interoperability.
- QGIS project export for technical GIS users.
- COG/VRT-oriented outputs for advanced raster workflows.

### Why export matters here

This is not just dashboard software. Field teams, GIS analysts, and administrators all need outputs in different formats, and the system supports that explicitly.

## Project Structure

```text
consorcio-canalero/
|- consorcio-web/              # React frontend
|- gee-backend/                # FastAPI backend
|  `- app/
|     |- api/v2/               # Router aggregation
|     |- auth/                 # JWT + OAuth
|     |- db/                   # Base, sessions, migrations
|     |- domains/              # Screaming Architecture business domains
|     |- core/                 # Logging, rate limiting, exceptions
|     `- shared/               # Cross-domain utilities
|- scripts/                    # ETLs and support scripts
|- gee/                        # Google Earth Engine scripts
|- martin/                     # Tile-server configuration
|- nginx/                      # Reverse proxy config
|- .github/workflows/          # CI/CD pipelines
|- docker-compose.yml          # Local/dev stack
|- docker-compose.prod.yml     # Production stack
|- docker-compose.deploy.yml   # Deploy-specific stack
`- DEPLOY.md                   # Deployment guide
```

Related repo docs:

- `gee-backend/README.md` for backend-specific guidance.
- `consorcio-web/README.md` for frontend-specific guidance.
- `DEPLOY.md` for infrastructure and rollout details.

## Environment Variables

Minimum backend variables:

```env
DATABASE_URL=postgresql://...
JWT_SECRET=...
REDIS_URL=redis://...
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
GEE_SERVICE_ACCOUNT=...
GEE_PRIVATE_KEY_PATH=/path/to/key.json
```

Minimum frontend variables:

```env
VITE_API_URL=http://localhost:8000
VITE_MARTIN_URL=http://localhost:3001
```

Production deployment also uses public URLs such as `MARTIN_PUBLIC_URL`, `FRONTEND_URL`, and `API_BASE_URL`. See `DEPLOY.md` for the server-side setup.

## Quick Start

### Recommended setup script

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh
```

### Manual local setup

```bash
# Backend
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd consorcio-web
npm install
cp .env.example .env
npm run dev
```

### Docker setup

```bash
docker compose up -d
docker compose up -d postgres redis
```

## API Surface

All current endpoints are grouped under `/api/v2`, with interactive docs typically available at `/docs` and `/redoc`.

| Prefix | Domain | Auth |
|--------|--------|------|
| `/api/v2/auth/*` | Authentication and user profile | Variable |
| `/api/v2/padron/*` | Member registry | Operator+ |
| `/api/v2/denuncias/*` | Citizen reports | Public submit, Operator+ manage |
| `/api/v2/finanzas/*` | Finance workflows | Operator+ |
| `/api/v2/tramites/*` | Procedures and tracking | Operator+ |
| `/api/v2/reuniones/*` | Meetings and agenda | Operator+ |
| `/api/v2/capas/*` | Layer management | Operator+ |
| `/api/v2/geo/*` | Geo processing and GEE workflows | Operator+ |
| `/api/v2/monitoring/*` | Suggestions and analysis tracking | Variable |
| `/api/v2/settings/*` | System settings | Operator+ read, Admin write |
| `/api/v2/public/*` | Public branding/viewer services | No auth |
| `/api/v2/admin/*` | Admin workflows such as invitations and user management | Admin |

## Testing

### Backend tests

```bash
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v
pytest tests/new/ -v --cov=app
ruff check .
ruff format --check .
```

Backend testing notes:

- `gee-backend/tests/new/` holds the newer architecture-focused tests.
- The documented pattern is real-database testing with transactional isolation instead of mocking away persistence.
- There are integration tests around Martin-backed public layer catalog behavior.

### Frontend tests

```bash
cd consorcio-web
npm run test
npm run test:coverage
npm run lint
```

### E2E and quality checks

```bash
cd consorcio-web
npx playwright test
```

What is covered in practice:

- Vitest and Testing Library for components, hooks, stores, and route-level behavior.
- Playwright configs and suites under `consorcio-web/tests/e2e/`.
- Accessibility-focused Playwright setup under `consorcio-web/tests/accessibility/`.
- Stryker-based mutation testing is configured in the frontend repo.

## Deployment

The repo is designed around a split deployment model.

### Frontend deploy

Cloudflare Pages serves the React application.

- Root directory: `consorcio-web`
- Build command: `npm run build`
- Output directory: `dist`
- Environment variables include `VITE_API_URL` and, when applicable, `VITE_MARTIN_URL`
- `_headers` and `_redirects` support SPA routing and security/cache policy

### Backend and services deploy

Hetzner-hosted services run the operational backend stack.

- FastAPI API service.
- PostgreSQL + PostGIS.
- Redis.
- Celery/geo worker.
- Martin tile server.

The production docs also reference GHCR images and rollout through Docker Compose on the server.

### Operational note

The frontend and backend are intentionally decoupled so the public web app can deploy quickly while data, tiles, and worker services remain under controlled infrastructure.

## CI/CD Notes

The repository includes GitHub Actions workflows for backend, frontend, deploy, Pages, Fly, and CodeQL concerns.

At a high level:

- Frontend pushes can trigger Cloudflare Pages builds automatically.
- Backend changes run CI checks and can build/publish container images.
- Production rollout is documented in `DEPLOY.md`, including optional webhook-based server updates.
- The first build path documented in `DEPLOY.md` publishes backend and geo-worker images to GHCR.

## License

MIT License. See [LICENSE](LICENSE).

Built for **Consorcio Canalero 10 de Mayo** in Marcos Juárez, Cordoba, Argentina.
