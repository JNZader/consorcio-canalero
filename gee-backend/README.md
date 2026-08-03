# Consorcio Canalero 10 de Mayo · Backend

API y motor de procesamiento geoespacial del **Consorcio Canalero 10 de Mayo** — departamento Unión, Córdoba, Argentina.

Backend FastAPI con arquitectura por dominios (Screaming Architecture), PostgreSQL+PostGIS, integración con Google Earth Engine y workers Celery para análisis pesados.

---

## Índice

- [Stack](#stack)
- [Arquitectura](#arquitectura)
- [Dominios](#dominios)
- [Capacidades geoespaciales](#capacidades-geoespaciales)
- [Sistema de auth y roles](#sistema-de-auth-y-roles)
- [Background jobs](#background-jobs)
- [Estructura](#estructura)
- [Inicio rápido](#inicio-rápido)
- [Variables de entorno](#variables-de-entorno)
- [Migraciones](#migraciones)
- [Tests](#tests)
- [Lint y format](#lint-y-format)
- [API](#api)
- [ETLs y scripts](#etls-y-scripts)
- [Generación de PDFs](#generación-de-pdfs)

---

## Stack

| Componente | Tecnología |
|------------|------------|
| **Framework** | FastAPI |
| **Lenguaje** | Python 3.11+ |
| **ORM** | SQLAlchemy 2.0 (declarative + Mapped) |
| **Migrations** | Alembic |
| **Schemas** | Pydantic v2 |
| **Auth** | fastapi-users (JWT + OAuth2) |
| **Base de datos** | PostgreSQL + PostGIS |
| **GIS ORM extension** | GeoAlchemy2 |
| **Geo processing** | Shapely · Rasterio · Fiona · GDAL · WhiteboxTools |
| **Earth Engine** | earthengine-api |
| **3D / Visualización** | PyVista |
| **Jobs async** | Celery + Redis |
| **PDFs** | ReportLab |
| **Logging** | structlog (estructurado, JSON-friendly) |
| **Tests** | Pytest + Pytest-cov + Hypothesis |
| **Lint / Format** | Ruff |
| **HTTP server** | Uvicorn |
| **Containers** | Docker + Docker Compose |

---

## Arquitectura

**Screaming Architecture**: cada dominio bajo `app/domains/` declara su propia estructura interna y expone routers a través de `api/v2/`.

Cada dominio sigue el patrón:

```
domain/
├── models.py       # SQLAlchemy 2.0 (Mapped, mapped_column)
├── schemas.py      # Pydantic v2 (request/response)
├── repository.py   # Data access (SELECT/INSERT/UPDATE)
├── service.py      # Business logic, orquesta repository + reglas
└── router.py       # FastAPI router (HTTP layer)
```

Base classes en `app/db/base.py`: `UUIDMixin`, `TimestampMixin`, `Base`.

**Convenciones**:

- UUIDs como primary keys.
- Timestamps (`created_at`, `updated_at`) en todas las tablas.
- Pydantic con `model_config = ConfigDict(from_attributes=True)`.
- Repositorios stateless que reciben `db: Session` como primer arg.
- Services orquestan repositorios y levantan `HTTPException` en errores de negocio.
- Routers thin: solo HTTP, delegan al service.

---

## Dominios

### `padron`
Registro maestro de consorcistas con CUIT, fracciones, derechos de agua y cuotas. Categorización (pequeño propietario, empresa, institución), estados (activo, suspendido, al día, deudor) e **importación en lote desde CSV/XLSX** con validación.

### `denuncias`
Reportes ciudadanos públicos con foto adjunta y geolocalización. Estados (abierta, en progreso, resuelta, rechazada), historial completo de cambios, filtros por cuenca y estadísticas agregadas (denuncias por mes, tiempo promedio de respuesta).

### `tramites`
Expedientes administrativos internos con tipo, prioridad y estado. Sistema de **seguimiento cronológico** con comentarios de cada operador. **Exportación a PDF** del expediente completo.

### `finanzas`
Contabilidad anual: ingresos por categoría, gastos por rubro, presupuesto anual, **análisis de ejecución** (proyectado vs. real) y **resumen anual exportable a PDF**.

### `reuniones`
Calendario de asambleas y reuniones de directorio con **agenda colaborativa**, vinculación automática de sugerencias ciudadanas y **orden del día exportable a PDF**.

### `capas`
CRUD de capas raster/vector mostradas en el visor. Distinción **públicas vs. operador**, reordenamiento drag-and-drop. Las capas pueden originarse en GEE, archivos estáticos o tablas PostGIS.

### `monitoring`
Sugerencias ciudadanas públicas + **dashboard integrado** con KPIs cruzados (denuncias, trámites, finanzas) + tracking persistente de análisis GEE ejecutados.

### `settings`
Configuración por deployment (general, branding, territorio, análisis, contacto). **Endpoint público de branding** (sin auth) para que el viewer cargue logo + colores. Persistencia de imagen satelital seleccionada del visor y comparador antes/después.

### `geo`
El dominio más amplio. Subdivido en cinco áreas:

#### `geo` (core)
- Bundles de cuencas (crear, listar, actualizar).
- Catálogo de capas y jerarquía territorial.

#### `geo` — GEE Layers & Imagery
- Listado dinámico de capas disponibles en Google Earth Engine.
- Tiles **Sentinel-2** parametrizables por fecha (true color, NDVI, MNDWI).
- Imágenes **Sentinel-1 SAR** para detección sin nubes.
- **Comparador SAR** entre dos fechas (detección de inundación).
- Listado de fechas disponibles por colección.
- Tiles históricos de eventos de inundación archivados.
- **Caminos coloreados por estado de servicio** + estadísticas de la red vial.

#### `geo` — Analysis
- Submission de análisis (flood detection, classification supervisada).
- Cola con estado (`pending`, `running`, `completed`, `failed`).
- Detalle de cada análisis con resultados.

#### `geo/intelligence`
- **Dashboard de inteligencia** con resumen de alertas, riesgo y conflictos.
- **HCI (Hydric Criticality Index)** — score de criticidad hídrica por zona, calculado a partir de slope, flow accumulation, TWI, proximidad a canal e historial de inundación. Pesos configurables.
- **Detección automática de conflictos** geoespaciales.
- **Simulación de escorrentía** desde un punto con Método Racional (caudal pico, tiempo de concentración, coeficiente).
- **Generación de zonificación** desde DEM + threshold (tarea async).
- **Alertas** activables/desactivables con condiciones evaluables.
- **Análisis composite** (flood risk + drainage need) y comparación con baseline.
- Vistas materializadas refrescables on-demand.

#### `geo/render`
- PNG 3D de **terreno + cuencas**.
- PNG de **escorrentía** con lluvia parametrizable.
- PNG de **zonas de riesgo hidráulico** coloreadas.
- **MP4 de animación fly-over** del terreno.

#### `geo/export`
- **Proyecto QGIS (.qgs)** descargable con todas las capas.

---

## Capacidades geoespaciales

### Capas raster procesadas

- DEM SRTM 30 m
- HAND (Height Above Nearest Drainage)
- Slope (pendiente)
- Flow accumulation
- TWI (Topographic Wetness Index)
- Hillshade
- Análisis SAR (cambios temporales)

### Modelos hidrológicos

- **Tiempo de concentración** — fórmula de Kirpich.
- **Caudal pico** — Método Racional (Q = C × I × A / 3.6).
- **TWI** — predisposición a saturación de agua.
- **HCI** — índice compuesto de criticidad hídrica.

### Integraciones GEE

- Colecciones: `COPERNICUS/S2`, `COPERNICUS/S1_GRD`, `USGS/SRTM/90_V4`.
- Procesamiento: NDVI, MNDWI, clasificación SAR.
- Tiles MVT para visualización web.
- Exportación COG / VRT.

### Procesamiento de terreno

- **WhiteboxTools** para análisis de DEM (pit fill, flow direction, accumulation, watershed delineation).
- **Rasterio** para I/O de GeoTIFF.
- **PyVista** para renderizado 3D.

---

## Sistema de auth y roles

### Roles

| Rol | Permisos |
|-----|----------|
| `admin` | Todos los dominios + settings + delete + invitaciones |
| `operador` | CRUD en dominios principales · lectura de settings |
| `ciudadano` | Crear denuncias y sugerencias (sin auth) |

### Mecanismos

- **JWT bearer** con fastapi-users (`Authorization: Bearer ...` desde el frontend).
- **OAuth2 (Google)** opcional como segundo método de identidad.
- **Sistema de invitaciones**: admin invita operadores por email con token de 24 h.
- Dependencias de auth con **lazy import** para evitar circular dependencies.

### Dependencias de FastAPI

- `require_admin` — solo admin.
- `require_admin_or_operator` — admin + operador.
- `require_authenticated` — cualquier usuario logueado.

---

## Background jobs

Tareas Celery se encolan en Redis y las procesa el servicio `geo-worker`.

| Tarea | Función |
|-------|---------|
| `task_dem_pipeline_full` | Pipeline DEM → HAND → Slope → TWI |
| `task_export_geo_bundle` | Empaquetado de capas para descarga |
| `task_generate_zonification` | Zonificación operativa desde DEM + threshold |
| `task_calculate_hci_all_zones` | Cálculo HCI batch para todas las zonas |
| `task_detect_all_conflicts` | Detección masiva de conflictos geoespaciales |
| `task_composite_analysis_task` | Análisis composite flood risk + drainage need |

Cada tarea registra estado en BD; el frontend hace polling de `/api/v2/geo/analysis/{id}` para mostrar progreso.

---

## Estructura

```
gee-backend/
├── app/
│   ├── main.py                       # Entry point FastAPI
│   ├── api/
│   │   └── v2/                       # Aggregator de routers v2
│   ├── auth/                         # fastapi-users (JWT + OAuth)
│   ├── db/
│   │   ├── base.py                   # Base, UUIDMixin, TimestampMixin
│   │   ├── session.py                # Engine + SessionLocal
│   │   └── migrations/               # Alembic versions
│   ├── domains/                      # 10 dominios (Screaming Architecture)
│   │   ├── padron/
│   │   ├── denuncias/
│   │   ├── tramites/
│   │   ├── finanzas/
│   │   ├── reuniones/
│   │   ├── capas/
│   │   ├── monitoring/
│   │   ├── settings/
│   │   └── geo/
│   │       ├── intelligence/         # HCI, conflictos, zonas, alertas, composite
│   │       ├── render/               # 3D PNG/MP4
│   │       └── (otros submódulos)
│   ├── core/                         # Logging, exceptions, rate limiting
│   └── shared/                       # Utilidades cross-domain
├── tests/
│   └── new/                          # Tests de la nueva arquitectura
│       ├── conftest.py               # Fixtures: db, db_session_factory, test_engine
│       └── (tests por dominio)
├── alembic.ini
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── pytest.ini
├── ruff.toml
└── .env.example
```

---

## Inicio rápido

### Setup local

```bash
cd gee-backend

# Crear venv
python3 -m venv venv && source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt -r requirements-dev.txt

# Configurar entorno
cp .env.example .env
# Editar DATABASE_URL, JWT_SECRET, REDIS_URL, GEE credentials

# Migrar base de datos
alembic upgrade head

# Levantar el servidor
uvicorn app.main:app --reload
```

API disponible en `http://localhost:8000`. Docs interactivas en `/docs` y `/redoc`.

### Setup con Docker

Desde la raíz del repo:

```bash
docker compose up -d backend postgres redis
docker compose logs -f backend
```

---

## Variables de entorno

```env
# Base de datos
DATABASE_URL=postgresql://consorcio:consorcio_dev@localhost:5432/consorcio

# Auth
JWT_SECRET=<openssl rand -hex 32>
JWT_LIFETIME_SECONDS=3600

# OAuth (opcional)
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...

# Redis (Celery broker + cache)
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=http://localhost:3000,http://localhost:5173

# Google Earth Engine
GEE_SERVICE_ACCOUNT=<email-cuenta-servicio>
GEE_PRIVATE_KEY_PATH=/path/to/key.json
```

Ver `.env.example` para la lista completa.

---

## Migraciones

```bash
# Aplicar migraciones pendientes
alembic upgrade head

# Crear nueva migración (autogenerate)
alembic revision --autogenerate -m "descripcion"

# Bajar una migración
alembic downgrade -1

# Ver historial
alembic history
```

Las migraciones viven en `app/db/migrations/versions/`.

---

## Tests

### Configuración

Los tests usan **PostgreSQL real** con transaction-per-test y rollback automático (sin mocking de data access).

Fixtures principales en `tests/new/conftest.py`:

- `db` — sesión por test con rollback al final.
- `db_session_factory` — factory para dependency override.
- `test_engine` — engine session-scoped + creación de tablas.

### Comandos

```bash
# Todos los tests
pytest tests/new/ -v

# Con cobertura
pytest tests/new/ -v --cov=app --cov-report=term-missing

# Un dominio específico
pytest tests/new/test_padron/ -v

# Un test puntual
pytest tests/new/test_denuncias/test_service.py::test_crear_denuncia -v
```

---

## Lint y format

```bash
# Check
ruff check .

# Check + format
ruff check . && ruff format --check .

# Autofix
ruff check . --fix
ruff format .
```

Configuración en `ruff.toml`.

---

## API

Todos los endpoints bajo `/api/v2`. Documentación interactiva:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

| Prefijo | Dominio | Auth |
|---------|---------|------|
| `/api/v2/auth/*` | Login, registro, perfil | Variable |
| `/api/v2/padron/*` | Padrón | Operador+ |
| `/api/v2/denuncias/*` | Denuncias | Público (POST) / Operador+ |
| `/api/v2/finanzas/*` | Finanzas | Operador+ |
| `/api/v2/tramites/*` | Trámites + seguimiento | Operador+ |
| `/api/v2/reuniones/*` | Reuniones + agenda | Operador+ |
| `/api/v2/capas/*` | Capas del mapa | Operador+ |
| `/api/v2/geo/*` | Geo + GEE + intelligence | Operador+ |
| `/api/v2/monitoring/*` | Sugerencias + análisis tracking | Variable |
| `/api/v2/settings/*` | Configuración | Operador+ (read) / Admin (write) |
| `/api/v2/public/*` | Viewer público + branding | Sin auth |
| `/api/v2/admin/publish/*` | Publicación de capas | Admin |
| `/api/v2/admin/users/*` | Gestión de usuarios | Admin |
| `/api/v2/admin/invitations/*` | Invitaciones | Admin |

---

## ETLs y scripts

Los ETLs viven en la carpeta `scripts/` de la raíz del repo. Convierten archivos KMZ exportados por el equipo de relevamiento en GeoJSON estáticos servidos por el frontend.

| ETL | Input | Output |
|-----|-------|--------|
| `etl_canales` | `Canales_existentes_v3.kmz` + `Propuestas_v3.kmz` | `consorcio-web/public/capas/canales/` |
| `etl_pilar_verde` | KMZs de agroforestación | `consorcio-web/public/capas/pilar-verde/` |
| `etl_escuelas` | KMZ de escuelas rurales | `consorcio-web/public/capas/escuelas/` |

Cada ETL tiene su propio README en `scripts/etl_*/README.md` con detalles de invocación y schema esperado.

Ejecución típica:

```bash
source gee-backend/venv/bin/activate
python scripts/etl_canales.py
```

---

## Generación de PDFs

ReportLab se usa para generar:

- Trámites (con seguimiento cronológico).
- Órdenes del día de reuniones.
- Resúmenes financieros anuales.

Todos respetan el branding (logo, colores, nombre) configurado en `settings`.

Templates en `app/shared/pdf_templates/` o por dominio en `app/domains/{dominio}/pdf/`.

---

Desarrollado para el **Consorcio Canalero 10 de Mayo** — departamento Unión, Córdoba, Argentina.
