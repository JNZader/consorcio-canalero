<div align="center">

# Consorcio Canalero 10 de Mayo

### Plataforma integral de gestión, monitoreo y análisis hídrico

**GIS-powered water management system** for the Consorcio Canalero 10 de Mayo — Bell Ville, Córdoba, Argentina. Self-hosted, clone-and-deploy ready. One system for drainage infrastructure, member registry, finances, citizen engagement, and geospatial intelligence.

<!-- TODO: Add hero screenshot here — dashboard with map visible -->
![Dashboard Preview](#)

[![Live Demo](https://img.shields.io/badge/demo-live-success?style=flat-square)](https://consorcio-canalero.pages.dev)
[![Stack: Python](https://img.shields.io/badge/backend-Python%203.11-blue?style=flat-square)](https://fastapi.tiangolo.com/)
[![Stack: React](https://img.shields.io/badge/frontend-React%2019-61dafb?style=flat-square)](https://react.dev/)
[![Stack: PostgreSQL](https://img.shields.io/badge/db-PostgreSQL%20%2B%20PostGIS-336791?style=flat-square)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

[🌐 Live Demo](https://consorcio-canalero.pages.dev) · [🚀 Quick Start](#quick-start) · [📚 API Docs](#api)

</div>

---

## ✨ Key Features

<details>
<summary><b>🗺️ GIS Monitoring & Intelligence</b></summary>

- Interactive map viewer with MapLibre GL + PMTiles + PostGIS vector layers
- Google Earth Engine integration: Sentinel-1 SAR, Sentinel-2 multispectral, DEM analysis
- **HCI (Hydric Criticality Index)** — composite risk score per zone with configurable weights
- Automated flood detection, runoff simulation (Rational Method), and conflict detection
- 3D terrain rendering (PyVista) + fly-over animation export
- Before/after satellite comparison and NDVI/water-index tiles

<!-- TODO: Add screenshot/GIF of GIS map viewer here -->

</details>

<details>
<summary><b>📋 Citizen Reports (Denuncias)</b></summary>

- Public endpoint — no login required to submit a report
- **Photo upload + map-pin geolocation** on every submission
- State machine: open → in progress → resolved / rejected
- Full audit trail (who changed what, when)
- Operator dashboard with filters, zone heatmaps, and response-time KPIs

<!-- TODO: Add screenshot of citizen report form here -->

</details>

<details>
<summary><b>⚙️ Admin Workflows</b></summary>

- **Padrón** — member registry with CUIT, water rights, fractions, bulk CSV/XLSX import
- **Trámites** — administrative proceedings with priority tracking + PDF export
- **Finanzas** — annual budget, income/expense tracking, execution analysis, PDF summaries
- **Reuniones** — meetings + collaborative agenda + automatic citizen-suggestion linking
- **Settings** — per-deployment branding (logo, colors, parameters), public branding endpoint

<!-- TODO: Add screenshot of admin panel here -->

</details>

<details>
<summary><b>📄 PDF & Data Export</b></summary>

- Branded PDFs: proceeding records, meeting agendas, financial summaries, asset data sheets
- KMZ exports for Google Earth with automatic PII stripping
- CSV, GeoJSON, QGIS project (.qgs), Cloud-Optimized GeoTIFF
- All exports respect branding settings (logo, colors, name)

<!-- TODO: Add screenshot of PDF export here -->

</details>

<details>
<summary><b>🔒 Auth & Roles</b></summary>

| Role | Access |
|------|--------|
| `admin` | All domains + settings + delete + invitations |
| `operador` | CRUD on main domains, read settings |
| `ciudadano` | Public reports & suggestions (no auth required) |

- JWT via fastapi-users (httpOnly cookie, auto-refresh)
- Optional Google OAuth as second identity factor
- Invitation system with 24 h activation token

</details>

---

## 🛠️ Tech Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | FastAPI · Python 3.11+ · SQLAlchemy 2.0 · Alembic · Pydantic v2 · Celery · Redis · ReportLab |
| **Frontend** | React 19 · TypeScript · Vite 7 · Mantine v8 · TanStack Router/Query · Zustand · MapLibre GL |
| **GIS** | PostGIS · GeoAlchemy2 · Google Earth Engine · Rasterio · GDAL · WhiteboxTools · Shapely · PMTiles (Martin) |
| **Auth** | fastapi-users · JWT · Google OAuth |
| **Testing** | Pytest · Vitest · Playwright (E2E) · Stryker (mutation) |
| **Infra** | Docker Compose · PostgreSQL+PostGIS · Nginx · Coolify (Hetzner) · Cloudflare Pages · GitHub Actions |

> Built with **Screaming Architecture** — each domain has its own `models · schemas · repository · service · router`.

---

## 🗺️ Geospatial Capabilities

### Vector Layers

Watersheds · canals (surveyed + proposed) · rural roads · schools · green-pillar zones · operational/conflict areas · active alerts · cadastral soils

### Raster & DEM Products

SRTM 30 m DEM · HAND · Slope · Flow accumulation · TWI · Sentinel-2 NDVI · Sentinel-1 SAR

### Analyses

- **SAR flood detection** — before/after comparison, cloud-free
- **Hydrological modeling** — Kirpich concentration time + Rational Method peak flow
- **Supervised classification** (land cover, flood extent)
- **HCI** — hydric criticality index per zone
- **TWI** — water saturation predisposition
- **Automated conflict detection** — geometric overlap between infrastructure, properties, and risk zones

### GEE Integrations

Collections: `COPERNICUS/S2`, `COPERNICUS/S1_GRD`, `USGS/SRTM/90_V4`. MVT tiles, COG/VRT export.

---

## 🏗️ Project Structure

```
consorcio-canalero/
├── consorcio-web/              # React frontend (Vite 7)
├── gee-backend/                # FastAPI backend
│   └── app/
│       ├── api/v2/             # Router aggregator
│       ├── auth/               # JWT + OAuth
│       ├── db/                 # Base, session, Alembic migrations
│       ├── domains/            # 10 domains (Screaming Architecture)
│       ├── core/               # Logging, exceptions, rate limiting
│       └── shared/             # Cross-domain utilities
├── scripts/                   # ETLs (canales, pilar verde, escuelas)
├── gee/                        # Google Earth Engine scripts
├── nginx/                      # Reverse proxy config
├── martin/                     # PMTiles server config
└── docker-compose.yml          # Full dev stack
```

Each domain: `models.py → schemas.py → repository.py → service.py → router.py`

---

## 🚀 Quick Start

### `setup.sh` (recommended)

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh
```

### Manual

```bash
# Backend
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env        # Fill in real values
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (another terminal)
cd consorcio-web
npm install
cp .env.example .env         # VITE_API_URL → backend
npm run dev
```

### Docker

```bash
docker compose up -d                        # Full stack
docker compose up -d postgres redis          # Dependencies only
```

### Minimum env vars

**Backend** (`gee-backend/.env`): `DATABASE_URL`, `JWT_SECRET`, `REDIS_URL`, `CORS_ORIGINS`, `GEE_SERVICE_ACCOUNT`, `GEE_PRIVATE_KEY_PATH`

**Frontend** (`consorcio-web/.env`): `VITE_API_URL`, `VITE_MARTIN_URL` (optional)

---

## 📡 API

All endpoints under `/api/v2`. Interactive docs at `/docs` (Swagger) and `/redoc`.

| Prefix | Domain | Auth |
|--------|--------|------|
| `/api/v2/auth/*` | Login, register, user profile | Variable |
| `/api/v2/padron/*` | Consorcista registry | Operator+ |
| `/api/v2/denuncias/*` | Citizen reports | Public (POST) / Operator+ |
| `/api/v2/finanzas/*` | Income, expenses, budget | Operator+ |
| `/api/v2/tramites/*` | Proceedings + tracking | Operator+ |
| `/api/v2/reuniones/*` | Meetings + agenda | Operator+ |
| `/api/v2/capas/*` | Map layers | Operator+ |
| `/api/v2/geo/*` | Geo processing + GEE | Operator+ |
| `/api/v2/monitoring/*` | Suggestions + analysis tracking | Variable |
| `/api/v2/settings/*` | System config | Operator+ (read) / Admin (write) |
| `/api/v2/public/*` | Public viewer + branding | No auth |
| `/api/v2/admin/*` | Users, invitations, publishing | Admin |

---

## 🧪 Testing

```bash
# Backend
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v                 # Run tests
pytest tests/new/ -v --cov=app       # With coverage

# Frontend
cd consorcio-web
npm run test                         # Unit (Vitest)
npx playwright test                  # E2E

# Lint
cd gee-backend && ruff check . && ruff format --check .
cd consorcio-web && npm run lint
```

---

## 🚢 Deploy

| Component | Platform | Details |
|-----------|----------|---------|
| Backend | **Coolify on Hetzner** | FastAPI + PostgreSQL + PostGIS + Redis + Celery + Martin |
| Frontend | **Cloudflare Pages** | Build: `npm run build`, output: `dist/` |
| CI/CD | GitHub Actions | test → build → deploy on push to `main` |

Full details in [DEPLOY.md](DEPLOY.md).

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

---

<div align="center">

Built for **Consorcio Canalero 10 de Mayo** — Bell Ville, Córdoba, Argentina.

</div>