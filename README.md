# Consorcio Canalero 10 de Mayo

Plataforma integral de gestión, monitoreo y análisis hídrico para el **Consorcio Canalero 10 de Mayo** — Bell Ville, Córdoba, Argentina.

Self-hosted, clone-and-deploy ready. Pensado para que un consorcio pueda operar de manera autónoma su infraestructura de drenaje, su padrón de afiliados, sus finanzas y su comunicación con la ciudadanía, todo desde un solo sistema.

---

## Índice

- [Visión general](#visión-general)
- [Stack](#stack)
- [Funcionalidades por dominio](#funcionalidades-por-dominio)
- [Capacidades geoespaciales](#capacidades-geoespaciales)
- [Sistema de exportación y reportes](#sistema-de-exportación-y-reportes)
- [Auth y roles](#auth-y-roles)
- [Background jobs](#background-jobs)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Inicio rápido](#inicio-rápido)
- [API](#api)
- [Tests](#tests)
- [Deploy](#deploy)
- [Licencia](#licencia)

---

## Visión general

La plataforma cubre cuatro grandes áreas de trabajo:

1. **Operación administrativa** — padrón de consorcistas, finanzas (ingresos/gastos/presupuesto/ejecución), trámites con seguimiento, agenda de reuniones.
2. **Participación ciudadana** — denuncias públicas con foto y geolocalización, sugerencias vinculables a la próxima reunión, viewer público sin login.
3. **Inteligencia geoespacial** — visor cartográfico interactivo, análisis con Google Earth Engine (Sentinel-1 SAR + Sentinel-2 multiespectral), modelado hidrológico, dashboard de inteligencia con índice de criticidad hídrica (HCI), zonificación automática y detección de conflictos.
4. **Configuración y branding** — settings por deployment (nombre, logo, colores, parámetros analíticos), selección de imagen satelital del visor, comparador antes/después.

---

## Stack

| Componente | Tecnología |
|------------|------------|
| **Frontend** | React 19 · TypeScript · Vite 7 · Mantine v8 · TanStack Router · TanStack Query · Zustand · MapLibre GL · PMTiles · Turf.js |
| **Backend** | FastAPI · Python 3.11+ · SQLAlchemy 2.0 · Alembic · Pydantic v2 |
| **Auth** | fastapi-users · JWT · Google OAuth (opcional) |
| **Base de datos** | PostgreSQL · PostGIS · GeoAlchemy2 |
| **Geo / Imágenes** | Google Earth Engine · Shapely · Rasterio · WhiteboxTools · GDAL |
| **3D / Visualización** | PyVista · Mapbox GL (capa terrain hybrid) |
| **Background jobs** | Celery · Redis |
| **PDFs** | ReportLab |
| **Logging** | structlog (estructurado) |
| **Tests** | Pytest · Vitest · Playwright (E2E) · Stryker (mutation) |
| **Lint / Format** | Ruff (Python) · Biome (TypeScript) |
| **CI/CD** | GitHub Actions · Docker Compose |
| **Deploy** | Coolify on Hetzner (backend) · Cloudflare Pages (frontend) · Martin (PMTiles server) |

---

## Funcionalidades por dominio

El backend usa **Screaming Architecture**: cada dominio bajo `gee-backend/app/domains/` tiene su propio `models.py`, `schemas.py`, `repository.py`, `service.py` y `router.py`.

### `padron` — Registro de consorcistas

- CRUD completo de consorcistas con CUIT, fracciones, derechos de agua, cuotas.
- Categorización: pequeño propietario, empresa, institución.
- Estados: activo, suspendido, al día, deudor.
- **Importación en lote desde CSV/XLSX** con validación automática.
- Estadísticas agregadas (total afiliados, deuda acumulada, distribución por categoría).

### `denuncias` — Reportes ciudadanos

- Endpoint público sin auth para que cualquier ciudadano reporte un problema.
- **Adjuntar fotos** + **selección de ubicación en mapa**.
- Sistema de estados: abierta · en progreso · resuelta · rechazada.
- Historial completo de cambios (quién, cuándo, qué).
- Filtros por estado y por cuenca geográfica.
- Estadísticas para operador (denuncias por mes, por zona, tiempo promedio de respuesta).

### `tramites` — Expedientes administrativos

- Registro de trámites internos con tipo, prioridad, estado.
- Sistema de seguimiento con comentarios cronológicos (cada operador puede agregar update).
- **Exportación a PDF** del expediente completo con su historial.
- Filtros por estado, tipo y prioridad.

### `finanzas` — Contabilidad anual

- Registro de **ingresos** (cuotas, subsidios, transferencias) por categoría y año.
- Registro de **gastos** (personal, operación, infraestructura) por rubro y año.
- **Presupuesto anual** con líneas presupuestarias.
- **Análisis de ejecución**: proyectado vs. real por rubro.
- **Resumen anual** con balance ingresos − gastos, **exportable a PDF**.

### `reuniones` — Asambleas y directorio

- Calendario de reuniones con tipo (asamblea, directorio, comisión).
- **Agenda colaborativa** con temas propuestos.
- **Vinculación automática de sugerencias** ciudadanas a la próxima reunión.
- **Orden del día exportable a PDF** con branding del consorcio.

### `capas` — Gestión de capas del mapa

- CRUD de capas raster/vector mostradas en el visor.
- Distinción **públicas vs. operador**: el viewer público solo ve las marcadas como tales.
- Reordenamiento drag-and-drop del orden de visualización.
- Origen de capa: GEE, archivo estático, tabla PostGIS.

### `monitoring` — Sugerencias y tracking de análisis

- **Sugerencias ciudadanas** públicas (sin auth) con categorización.
- Endpoint para listar sugerencias agendadas a la próxima reunión.
- Marcado de sugerencias incorporadas como obras concretas.
- **Dashboard integrado** con KPIs cruzados de denuncias, trámites y finanzas.
- Historial persistente de análisis GEE ejecutados.

### `settings` — Configuración por deployment

- Configuración categorizada: general, branding, territorio, análisis, contacto.
- **Endpoint público de branding** (`/api/v2/public/settings/branding`) para que el viewer cargue logo y colores sin requerir auth.
- Persistencia de la **imagen satelital seleccionada** del visor (Sentinel-2 + fecha).
- **Imagen de comparación temporal** (antes/después) para análisis visual.
- Pesos y umbrales configurables para los modelos de análisis.

### `geo` — Procesamiento geoespacial e inteligencia

El dominio más amplio. Se subdivide en cinco áreas:

#### Capas e imágenes GEE
- Listado dinámico de **capas disponibles en Google Earth Engine**.
- **Tiles Sentinel-2** parametrizables por fecha (visualización true color, NDVI, índices de agua).
- **Imágenes Sentinel-1 SAR** para detección sin nubes — útil en zonas de alta nubosidad.
- **Comparador SAR** entre dos fechas para detectar inundaciones.
- Listado de **fechas disponibles** por colección.
- Tiles históricos de eventos de inundación archivados.
- **Caminos coloreados por estado de servicio** + estadísticas de la red vial.

#### Análisis GEE
- Submission de análisis (flood detection, classification supervisada, etc.).
- Cola de procesamiento con estado (`pending`, `running`, `completed`, `failed`).
- Detalle de cada análisis con resultados y referencias a tiles generados.

#### Inteligencia (`/intelligence/*`)
- **Dashboard de inteligencia** con resumen de alertas, riesgo hídrico y conflictos.
- **HCI (Hydric Criticality Index)** — score de criticidad hídrica por zona, calculado a partir de slope, flow accumulation, TWI, proximidad a canal e historial de inundación. Pesos configurables.
- **Detección automática de conflictos** geoespaciales (solapamientos entre infraestructura, propiedades y zonas de riesgo).
- **Simulación de escorrentía** desde un punto del mapa con Método Racional: caudal, tiempo de concentración, coeficiente de escorrentía.
- **Generación automática de zonificación** desde DEM + threshold (tarea async).
- **Sistema de alertas** activables/desactivables con condiciones evaluables.
- **Análisis composite** (flood risk + drainage need) y comparación con baseline.
- Vistas materializadas para acelerar consultas pesadas, refrescables on-demand.

#### Renderizado 3D (`/render/*`)
- PNG 3D de **terreno + cuencas**.
- PNG de **escorrentía** con lluvia parametrizable.
- PNG de **zonas de riesgo hidráulico** coloreadas.
- **MP4 de animación fly-over** del terreno.

#### Export
- **Proyecto QGIS (.qgs)** descargable con todas las capas configuradas.

---

## Capacidades geoespaciales

### Capas vectoriales del visor

- Cuencas hidrográficas
- Canales relevados (red existente del consorcio)
- Canales propuestos (con prioridad y código)
- Caminos rurales con codificación por estado de servicio
- Escuelas rurales
- Capas de pilar verde (agroforestación, BPA, porcentaje de forestación, zona ampliada)
- Zonas operativas y de conflicto
- Alertas activas
- Suelos catastrados

### Capas raster y derivados de DEM

- DEM SRTM 30 m
- HAND (Height Above Nearest Drainage)
- Slope (pendiente)
- Flow accumulation
- TWI (Topographic Wetness Index)
- NDVI desde Sentinel-2
- SAR desde Sentinel-1

### Análisis disponibles

- **Detección de inundaciones SAR** — comparación Sentinel-1 antes/después, sin requerir cobertura óptica libre de nubes.
- **Modelado hidrológico** — Kirpich (tiempo de concentración) + Método Racional (caudal pico).
- **Clasificación supervisada** sobre GEE (cobertura, suelos, extensión de inundación).
- **HCI** — índice de criticidad hídrica por zona.
- **TWI** — predisposición a saturación de agua.
- **Detección de conflictos** geoespaciales automatizada.

### Integraciones GEE

- Colecciones: `COPERNICUS/S2`, `COPERNICUS/S1_GRD`, `USGS/SRTM/90_V4`.
- Procesamiento: NDVI, MNDWI, clasificación SAR.
- Tiles MVT para visualización web eficiente.
- Exportación COG / VRT.

---

## Sistema de exportación y reportes

### PDFs generados

| Documento | Contenido |
|-----------|-----------|
| Trámite | Datos del expediente + seguimiento cronológico |
| Ficha técnica de activo | Datos del activo + bitácora de mantenimiento |
| Orden del día de reunión | Agenda con temas propuestos |
| Resumen financiero anual | Balance ingresos − gastos por rubro |

Todos respetan el branding (logo, colores, nombre del consorcio) configurado en `settings`.

### KMZ exportables

- KMZ de capas del consorcio para abrir en Google Earth.
- **PII strip automático**: se remueven datos sensibles del padrón antes de exportar.
- Estilos KML personalizados por tipo de capa.

### Otros formatos

- CSV — padrón de consorcistas, historial de trámites.
- GeoJSON — zonas, cuencas, puntos de conflicto (para SIG externos).
- Proyecto QGIS (.qgs) con todas las capas.
- COG (Cloud-Optimized GeoTIFF) para análisis avanzado offline.

---

## Auth y roles

### Roles

| Rol | Permisos |
|-----|----------|
| `admin` | Todos los dominios + settings + delete + invitaciones |
| `operador` | CRUD en dominios principales · lectura de settings |
| `ciudadano` | Crear denuncias y sugerencias (sin auth requerida) |

### Mecanismos

- **JWT** vía fastapi-users en httpOnly cookie con refresh automático antes de expirar.
- **Google OAuth** opcional como segundo factor de identidad.
- **Sistema de invitaciones**: el admin invita operadores por email con token de activación de 24 h.

---

## Background jobs

Tareas Celery + worker GEE corren en su propio servicio Docker.

### Tareas registradas

- `task_dem_pipeline_full` — pipeline DEM → HAND → Slope → TWI.
- `task_export_geo_bundle` — empaquetado de capas para descarga.
- `task_generate_zonification` — zonificación operativa desde DEM + threshold.
- `task_calculate_hci_all_zones` — cálculo HCI batch para todas las zonas.
- `task_detect_all_conflicts` — detección masiva de solapamientos geométricos.
- `task_composite_analysis_task` — análisis composite flood risk + drainage need.

### Tracking

Cada tarea registra su estado en BD; el frontend hace polling de `/api/v2/geo/analysis/{id}` para mostrar progreso.

---

## Estructura del proyecto

```
consorcio-canalero/
├── consorcio-web/              # React frontend (Vite 7)
├── gee-backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/v2/             # Aggregator de routers v2
│   │   ├── auth/               # fastapi-users (JWT + OAuth)
│   │   ├── db/                 # Base, session, Alembic migrations
│   │   ├── domains/            # 10 dominios (Screaming Architecture)
│   │   ├── core/               # Logging, exceptions, rate limiting
│   │   └── shared/             # Utilidades cross-domain
│   ├── tests/new/              # Tests de la nueva arquitectura
│   └── alembic.ini
├── scripts/                    # ETLs y utilities
│   ├── etl_canales/            # ETL de canales relevados + propuestas (KMZ → GeoJSON)
│   ├── etl_pilar_verde/        # ETL de capas de agroforestación
│   └── etl_escuelas/           # ETL de escuelas rurales
├── gee/                        # Scripts de Google Earth Engine
├── nginx/                      # Reverse proxy config
├── martin/                     # PMTiles server config
├── docs/                       # Documentación
├── openspec/                   # Specs SDD
├── docker-compose.yml          # Stack completo dev
├── docker-compose.prod.yml     # Stack producción
├── docker-compose.deploy.yml   # Config específica de deploy
├── martin-config.deploy.yaml   # Config Martin (tiles)
├── Makefile
├── setup.sh                    # Script clone-and-deploy
├── DEPLOY.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Inicio rápido

### Con `setup.sh` (recomendado)

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
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (en otra terminal)
cd consorcio-web
npm install
cp .env.example .env  # VITE_API_URL apuntando al backend
npm run dev
```

### Docker

```bash
docker compose up -d                    # Stack completo
docker compose up -d postgres redis     # Solo dependencias
docker compose logs -f backend          # Seguir logs del backend
```

### Variables de entorno mínimas

**Backend** (`gee-backend/.env`):
```env
DATABASE_URL=postgresql://consorcio:consorcio_dev@localhost:5432/consorcio
JWT_SECRET=<openssl rand -hex 32>
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
GEE_SERVICE_ACCOUNT=<email-cuenta-servicio>
GEE_PRIVATE_KEY_PATH=/path/to/key.json
```

**Frontend** (`consorcio-web/.env`):
```env
VITE_API_URL=http://localhost:8000
VITE_MARTIN_URL=http://localhost:3001  # opcional
```

---

## API

Todos los endpoints nuevos están bajo `/api/v2`. Documentación interactiva en `/docs` (Swagger UI) y `/redoc`.

| Prefijo | Dominio | Auth |
|---------|---------|------|
| `/api/v2/auth/*` | Login, registro, perfil de usuario | Variable |
| `/api/v2/padron/*` | Padrón de consorcistas | Operador+ |
| `/api/v2/denuncias/*` | Reportes ciudadanos | Público (POST) / Operador+ |
| `/api/v2/finanzas/*` | Ingresos, gastos, presupuesto | Operador+ |
| `/api/v2/tramites/*` | Trámites + seguimiento | Operador+ |
| `/api/v2/reuniones/*` | Reuniones + agenda | Operador+ |
| `/api/v2/capas/*` | Capas del mapa | Operador+ |
| `/api/v2/geo/*` | Procesamiento geoespacial + GEE | Operador+ |
| `/api/v2/monitoring/*` | Sugerencias + análisis tracking | Variable |
| `/api/v2/settings/*` | Configuración del sistema | Operador+ (read) / Admin (write) |
| `/api/v2/public/*` | Viewer público + branding | Sin auth |
| `/api/v2/admin/publish/*` | Publicación de capas | Admin |
| `/api/v2/admin/users/*` | Gestión de usuarios | Admin |
| `/api/v2/admin/invitations/*` | Invitaciones | Admin |

---

## Tests

```bash
# Backend
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v
pytest tests/new/ -v --cov=app

# Frontend
cd consorcio-web
npm run test
npm run test:coverage

# E2E
cd consorcio-web
npx playwright test

# Lint
cd gee-backend && ruff check . && ruff format --check .
cd consorcio-web && npm run lint
```

---

## Deploy

### Backend — Coolify on Hetzner

- Build desde `docker-compose.deploy.yml`
- Servicios: backend FastAPI, PostgreSQL+PostGIS, Redis, Celery worker, Martin tile server.
- Variables de entorno gestionadas desde Coolify UI.

### Frontend — Cloudflare Pages

- Build directory: `consorcio-web`
- Build command: `npm run build`
- Output: `dist`
- Headers de seguridad y cache definidos en `consorcio-web/public/_headers`.
- SPA fallback en `consorcio-web/public/_redirects`.

### CI/CD

- GitHub Actions: test → build → deploy en cada push a `main`.

Detalles completos en [DEPLOY.md](DEPLOY.md).

---

## Licencia

MIT License — ver [LICENSE](LICENSE).

---

Desarrollado para el **Consorcio Canalero 10 de Mayo** — Bell Ville, Córdoba, Argentina.
