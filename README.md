# Consorcio Canalero 10 de Mayo

Sistema integral de gestión para consorcios canaleros — Bell Ville, Córdoba, Argentina.

Self-hosted, clone-and-deploy ready.

## Stack

| Componente | Tecnología |
|------------|------------|
| **Frontend** | React 19, TypeScript, Vite, Mantine UI, Leaflet |
| **Backend** | FastAPI, Python 3.11+, SQLAlchemy 2.0, Alembic |
| **Auth** | JWT + Google OAuth (fastapi-users) |
| **Database** | PostgreSQL + PostGIS |
| **Geo** | Google Earth Engine, GDAL worker |
| **Queue** | Redis + Celery (async geo tasks) |
| **Testing** | Pytest (backend), Vitest (frontend), Playwright (E2E) |
| **CI/CD** | GitHub Actions, Docker Compose |
| **Deploy** | Coolify on Hetzner (backend), Cloudflare Pages (frontend) |

## Dominios

El backend usa **Screaming Architecture** — cada dominio bajo `gee-backend/app/domains/` tiene su propio `models/schemas/repository/service/router`:

| Dominio | Descripción |
|---------|-------------|
| `padron` | Registro de consorcistas (CUIT, representación, cuotas) |
| `denuncias` | Reportes ciudadanos con verificación de identidad |
| `finanzas` | Ingresos, gastos, presupuestos |
| `infraestructura` | Activos, bitácora de mantenimiento, fichas técnicas |
| `tramites` | Expedientes ante Recursos Hídricos |
| `capas` | Capas del mapa (publicación admin) |
| `geo` | Procesamiento geoespacial + GEE + intelligence dashboard |
| `monitoring` | Sugerencias + análisis GEE tracking |
| `reuniones` | Planificación de reuniones, orden del día |
| `settings` | Configuración por deployment (branding, territorio, contacto) |

Funcionalidades transversales: exportación PDF (5 tipos de documento), invitaciones de usuario, dashboard de inteligencia.

## Estructura del Proyecto

```
consorcio-canalero/
├── .codex/skills/              # Skills locales versionadas para asistentes
├── consorcio-web/              # React frontend (Vite)
├── gee-backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/v2/             # V2 API router aggregator
│   │   ├── auth/               # fastapi-users auth (JWT + OAuth)
│   │   ├── db/                 # Base, session, migrations (Alembic)
│   │   ├── domains/            # Screaming Architecture (10 dominios)
│   │   ├── core/               # Logging, exceptions, rate limiting
│   │   └── shared/             # Cross-domain utilities
│   └── tests/new/              # Tests nueva arquitectura
├── docker-compose.yml
├── docker-compose.prod.yml
├── setup.sh                    # Clone-and-deploy setup script
└── openspec/                   # SDD specs
```

## AI / Codex Skills del Proyecto

Este repo versiona skills locales en `.codex/skills/` para que el contexto del proyecto sea portable entre máquinas y reutilizable por futuros asistentes/agentes.

Actualmente incluye:

- `maplibre-tile-sources`
- `maplibre-pmtiles-patterns`
- `maplibre-mapbox-migration`

## Inicio Rápido

### Con setup.sh (recomendado)

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
cp .env.example .env  # Editar con valores reales
uvicorn app.main:app --reload

# Frontend (otra terminal)
cd consorcio-web
npm install
npm run dev
```

### Docker

```bash
docker compose up -d                    # Todos los servicios
docker compose up -d postgres redis     # Solo DB + cache
docker compose logs -f backend          # Seguir logs
```

## Variables de Entorno

**Backend** (`gee-backend/.env.example`):

```env
DATABASE_URL=postgresql://consorcio:consorcio_dev@localhost:5432/consorcio
JWT_SECRET=<openssl rand -hex 32>
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

**Frontend** (`consorcio-web/.env.example`): solo `VITE_API_URL`.

## API

Todos los endpoints nuevos bajo `/api/v2`. Documentación interactiva en `/docs`.

| Prefijo | Dominio | Auth |
|---------|---------|------|
| `/api/v2/auth/*` | Login, registro, usuarios | Varies |
| `/api/v2/padron/*` | Padrón de consorcistas | Operator+ |
| `/api/v2/denuncias/*` | Reportes ciudadanos | Operator+ |
| `/api/v2/finanzas/*` | Finanzas | Operator+ |
| `/api/v2/infraestructura/*` | Activos + mantenimiento | Operator+ |
| `/api/v2/tramites/*` | Trámites | Operator+ |
| `/api/v2/capas/*` | Capas del mapa | Operator+ |
| `/api/v2/geo/*` | Geo + GEE | Operator+ |
| `/api/v2/monitoring/*` | Sugerencias + análisis | Varies |
| `/api/v2/settings/*` | Configuración sistema | Operator+ / Admin |
| `/api/v2/public/*` | Viewer público, branding | Sin auth |

### Roles

Tres roles: `admin`, `operador`, `ciudadano`.

## Tests

```bash
# Backend
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v
pytest tests/new/ -v --cov=app

# Frontend
cd consorcio-web
npm run test

# Lint
cd gee-backend && ruff check . && ruff format --check .
```

## Deploy

- **Backend**: Coolify on Hetzner — builds from `docker-compose.prod.yml`
- **Frontend**: Cloudflare Pages — builds from `consorcio-web/`
- **CI/CD**: GitHub Actions pipeline (test → build → deploy)

## Licencia

MIT License — ver [LICENSE](LICENSE).

---

Desarrollado para el **Consorcio Canalero 10 de Mayo** — Bell Ville, Córdoba, Argentina.
