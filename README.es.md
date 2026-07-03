# Consorcio Canalero 10 de Mayo

Read this in: [English](README.md) · [Español](README.es.md)

Plataforma con GIS para la operación del consorcio canalero, monitoreo hidrológico y reportes públicos.

[![Live Demo](https://img.shields.io/badge/demo-live-success?style=flat-square)](https://consorcio-canalero.pages.dev)
[![Backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20Celery-blue?style=flat-square)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/frontend-React%2019%20%2B%20Vite-61dafb?style=flat-square)](https://react.dev/)
[![Database](https://img.shields.io/badge/db-PostgreSQL%20%2B%20PostGIS-336791?style=flat-square)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)

Demo: [consorcio-canalero.pages.dev](https://consorcio-canalero.pages.dev)

Capturas próximamente. El mayor diferencial del proyecto es el flujo de trabajo GIS: los reportes públicos, la operación diaria y la inteligencia hidrológica conectan todos con el mismo mapa y el mismo modelo de datos territorial.

## Resumen para portfolio

- Construido para un consorcio canalero real en Bell Ville, Córdoba, Argentina.
- Combina la gestión administrativa con inteligencia geoespacial, en vez de tratar al GIS como un visor aislado.
- Cubre padrón, denuncias, tramites, finanzas, reuniones, capas, monitoring, settings y geo en un único sistema desplegable.
- Usa PostGIS, Google Earth Engine, Martin/PMTiles y workers en segundo plano para terreno, imágenes y análisis de riesgo.
- Arquitectura self-hosted con despliegue frontend/backend separado: Cloudflare Pages para la web y servicios en Hetzner para API, tiles, jobs y datos.

## Por qué importa

El software municipal o de consorcios típico maneja el papeleo pero ignora el territorio. Las demos de GIS típicas impresionan pero se quedan cortas para la operación diaria.

Esta plataforma conecta ambos lados:

- Un ciudadano puede cargar una denuncia con fotos y ubicación en el mapa.
- Un operador puede clasificarla, relacionarla con zonas, caminos, canales o capas de riesgo, y seguir la respuesta.
- El consorcio puede gestionar socios, finanzas, trámites, reuniones y branding público desde el mismo sistema.
- Los perfiles técnicos pueden correr análisis de inundación, terreno e hidrología sobre la misma base geoespacial que usa la operación.

Casos de uso:

- Planificación de drenaje y mantenimiento de canales.
- Monitoreo de riesgo de inundación con SAR de Sentinel-1 y productos de terreno derivados del DEM.
- Recepción pública de reportes y sugerencias sin requerir login.
- Coordinación administrativa entre padrón, finanzas, trámites y reuniones.
- Exportación de datos GIS para equipos de campo, usuarios de QGIS y consumidores de Google Earth.

## Inicio rápido

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh
```

Arranque manual:

```bash
# Backend
cd gee-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# Frontend (nueva terminal)
cd consorcio-web
npm install
cp .env.example .env
npm run dev
```

Docker:

```bash
docker compose up -d
```

## Ir a la documentación técnica

- [README técnico](#readme-técnico)
- [Arquitectura](#arquitectura)
- [Dominios funcionales](#dominios-funcionales)
- [Capacidades geoespaciales](#capacidades-geoespaciales)
- [Autenticación y roles](#autenticación-y-roles)
- [Tareas en segundo plano](#tareas-en-segundo-plano)
- [Exportación y reportes](#exportación-y-reportes)
- [Testing](#testing)
- [Despliegue](#despliegue)

---

## README técnico

## Tabla de contenidos

- [Descripción general](#descripción-general)
- [Stack](#stack)
- [Arquitectura](#arquitectura)
- [Dominios funcionales](#dominios-funcionales)
- [Capacidades geoespaciales](#capacidades-geoespaciales)
- [Autenticación y roles](#autenticación-y-roles)
- [Tareas en segundo plano](#tareas-en-segundo-plano)
- [Exportación y reportes](#exportación-y-reportes)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Variables de entorno](#variables-de-entorno)
- [Inicio rápido](#inicio-rápido-1)
- [Superficie de la API](#superficie-de-la-api)
- [Testing](#testing)
- [Despliegue](#despliegue)
- [Notas de CI/CD](#notas-de-cicd)
- [Licencia](#licencia)

## Descripción general

Consorcio Canalero 10 de Mayo es una plataforma operativa self-hosted para organizaciones de gestión del agua. Combina flujos administrativos, participación ciudadana y análisis hidrológico/geoespacial en un solo sistema.

La plataforma cubre cuatro áreas amplias:

1. Operación administrativa: padrón, finanzas, tramites, reuniones y settings.
2. Participación pública: denuncias, sugerencias, branding público y acceso público al mapa.
3. Inteligencia geoespacial: capas interactivas del mapa, imágenes de Earth Engine, análisis derivado del terreno, scoring HCI y detección de conflictos.
4. Despliegue operativo: setup de clonar-y-desplegar, servicios en contenedores y hosting separado frontend/backend.

## Stack

| Capa | Tecnologías |
|------|-------------|
| Backend | FastAPI, Python 3.11, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Frontend | React 19, TypeScript, Vite 7, Mantine v8, TanStack Router, TanStack Query, Zustand |
| Base de datos | PostgreSQL, PostGIS, GeoAlchemy2 |
| GIS e imágenes | Google Earth Engine, Rasterio, GDAL, WhiteboxTools, Shapely, PyVista |
| Tiles vectoriales y mapas | MapLibre GL, PMTiles, Martin tile server |
| Procesamiento en segundo plano | Celery, Redis |
| Reportes | ReportLab, exportación de proyecto QGIS, exportación KMZ |
| Testing | Pytest, Vitest, Playwright, Stryker |
| Tooling | Ruff, Biome, Docker Compose, GitHub Actions |
| Hosting | Cloudflare Pages, Hetzner, GHCR |

Las versiones reflejan los manifiestos en `gee-backend/requirements.txt` y `consorcio-web/package.json`. Los contenedores del backend se construyen sobre `python:3.11-slim`; el geo worker se construye sobre la imagen GDAL de OSGeo para tener el tooling raster/vectorial nativo.

## Arquitectura

El backend sigue **Screaming Architecture**. La estructura del repositorio prioriza las capacidades de negocio por sobre las capas técnicas, así el código te dice qué hace el sistema: `padron`, `denuncias`, `tramites`, `finanzas`, `reuniones`, `capas`, `monitoring`, `settings`, `geo`.

Cada dominio bajo `gee-backend/app/domains/` es dueño de su propio corte interno:

```text
domain/
|- models.py       # Modelos SQLAlchemy
|- schemas.py      # Modelos Pydantic de request/response
|- repository.py   # Solo acceso a datos
|- service.py      # Reglas de negocio y orquestación
`- router.py       # Capa HTTP de FastAPI
```

Por qué importa:

- Las reglas de negocio quedan cerca de su dominio en vez de desparramadas en carpetas genéricas.
- Cada dominio puede evolucionar con límites más claros.
- El ruteo de la API queda fino, los repositorios se enfocan en la persistencia y los servicios contienen la lógica del caso de uso.
- El dominio geo puede crecer en submódulos especializados (por ejemplo el submódulo `intelligence`) sin arrastrar al resto del código a la complejidad GIS.

Convenciones base:

- Claves primarias UUID y timestamps en todas las tablas.
- Schemas Pydantic v2 con serialización amigable con el ORM.
- Repositorios stateless que reciben `db: Session`.
- Routers finos que delegan en los servicios.
- Infraestructura compartida en `app/core/`, `app/db/` y `app/shared/`.

La autenticación vive en un módulo dedicado `app/auth/` en vez de bajo `domains/`, y todos los routers de dominio se agregan bajo `/api/v2` en `app/api/v2/router.py`.

## Dominios funcionales

### `padron`

Registro maestro de consorcistas, incluyendo CUIT, fracciones, derechos de agua, cuotas, categoría y estado de cuenta.

- CRUD completo de registros de socios.
- Importación masiva CSV/XLSX con validación.
- Métricas agregadas como total de socios, deuda y distribución por categoría.

### `denuncias`

Reportes ciudadanos de cara al público con seguimiento operativo.

- Envío de reportes sin login.
- Carga de fotos y geolocalización sobre el mapa.
- Estados del flujo: abierta, en progreso, resuelta, rechazada.
- Historial de auditoría de las acciones del operador.
- Filtros y métricas de respuesta.

### `tramites`

Trámites administrativos y seguimiento interno de expedientes.

- Gestión de tipo, prioridad y estado.
- Comentarios de seguimiento cronológicos.
- Exportación del expediente completo a PDF.

### `finanzas`

Gestión financiera anual del consorcio.

- Seguimiento de ingresos por categoría.
- Seguimiento de gastos por partida presupuestaria.
- Definición de presupuesto anual.
- Análisis de ejecución: planificado vs. real.
- Exportación del resumen financiero anual a PDF.

### `reuniones`

Gestión de reuniones y orden del día.

- Calendario de reuniones por tipo.
- Construcción colaborativa del orden del día.
- Vinculación automática de sugerencias ciudadanas a la próxima reunión.
- Exportación del orden del día a PDF.

### `capas`

Gestión de capas del mapa.

- CRUD de capas raster y vectoriales.
- Visibilidad pública vs solo-operador.
- Ordenamiento y comportamiento de publicación en el visor.
- Las fuentes pueden venir de GEE, archivos estáticos o datos respaldados en PostGIS.

### `monitoring`

Flujos transversales de monitoreo y participación.

- Sugerencias públicas.
- KPIs de dashboard que abarcan denuncias, tramites y finanzas.
- Seguimiento persistente de los análisis GEE ejecutados.

### `settings`

Configuración del sistema por despliegue.

- Configuración general, de branding, de territorio, de análisis y de contacto.
- Endpoint público de branding para que el frontend cargue logo y colores sin auth.
- Persistencia de la imagen satelital seleccionada y soporte de comparación antes/después.
- Pesos y umbrales de análisis configurables.

### `geo`

El dominio más especializado, que maneja procesamiento espacial, imágenes, análisis de terreno e inteligencia.

Subáreas:

- Bundles geo centrales y jerarquía territorial.
- Catálogo de imágenes y capas respaldado en GEE.
- Jobs de análisis con estado de ejecución asincrónico.
- Un submódulo `intelligence` con endpoints para HCI, conflictos, zonificación, alertas y análisis compuesto.
- Soporte de visualización/exportación, incluida la generación de proyectos QGIS y salidas de terreno.

## Capacidades geoespaciales

### Capas vectoriales

- Cuencas.
- Canales relevados y proyectados.
- Caminos rurales con visualización del estado de servicio.
- Escuelas rurales.
- Pilar Verde y capas agroforestales relacionadas.
- Zonas operativas, áreas de conflicto y alertas.
- Datasets catastrales y de apoyo.

### Productos raster y derivados del DEM

- DEM Copernicus GLO-30 (`COPERNICUS/DEM/GLO30`).
- HAND.
- Pendiente.
- Acumulación de flujo.
- TWI.
- Hillshade.
- NDVI de Sentinel-2 y productos de agua/vegetación relacionados.
- Imágenes SAR de Sentinel-1 para análisis de inundación independiente de nubes.

### Capacidades de análisis

- Detección de inundación por SAR mediante comparación antes/después.
- Modelado de caudal de inundación: tiempo de concentración de Kirpich y caudal pico por Método Racional, persistidos en una tabla de resultados dedicada.
- HCI (Índice de Criticidad Hídrica) por zona.
- Detección de conflictos por solapamiento geométrico entre capas de infraestructura y riesgo.
- Zonificación automática a partir de la delineación de cuencas.
- Análisis compuesto de riesgo de inundación y necesidad de drenaje.
- Renderizado de terreno 3D y exportación de fly-over (PyVista, headless).

### Integración con Google Earth Engine

- Las colecciones usadas incluyen `COPERNICUS/S2_SR_HARMONIZED`, `COPERNICUS/S1_GRD` y `COPERNICUS/DEM/GLO30`.
- El sistema expone capas procesadas, fechas de imágenes y resultados de análisis de vuelta a la web app.
- Martin y PMTiles permiten una entrega eficiente del mapa para datos vectoriales más pesados.

## Autenticación y roles

Modelo de roles:

| Rol | Acceso |
|-----|--------|
| `admin` | Acceso total, escritura de settings, invitaciones, flujos de admin |
| `operador` | CRUD sobre dominios operativos, lectura de settings |
| `ciudadano` | Reportes y sugerencias públicas; la mayoría de los flujos públicos no requieren autenticación |

Mecanismos de autenticación:

- JWT vía tokens bearer de `fastapi-users`. El adaptador actual del frontend guarda la
  sesión en `sessionStorage` y envía `Authorization: Bearer ...` a `/api/v2/*`.
- Google OAuth opcional.
- Refresh tokens con un flujo `logout-all` que revoca los JWT emitidos previamente.
- Onboarding de operadores basado en invitaciones con tokens de activación.
- Dependencias de FastAPI como `require_admin`, `require_admin_or_operator` y guards de usuario autenticado.

## Tareas en segundo plano

El procesamiento asincrónico corre con Celery, usando Redis como broker/apoyo de cache. Los flujos pesados de geo o de exportación se mantienen deliberadamente fuera del camino de request/response. Las tareas de geo corren en una cola `geo` dedicada.

Nombres de tareas registrados (ver `gee-backend/app/domains/geo/`):

| Tarea | Propósito |
|-------|-----------|
| `geo.run_full_dem_pipeline` | Pipeline DEM a HAND, pendiente y TWI |
| `geo.composite_analysis` | Análisis compuesto de riesgo de inundación y necesidad de drenaje |
| `geo.intelligence.generate_zonification` | Genera zonificación operativa desde umbrales de cuenca/DEM |
| `geo.intelligence.calculate_hci_all` | Cálculo de HCI por lote sobre todas las zonas |
| `geo.intelligence.detect_all_conflicts` | Detección de conflictos geoespaciales por lote |
| `geo.intelligence.evaluate_alerts` | Evalúa condiciones de alertas operativas |
| `geo.warm_gee_layers` | Pre-calienta el cache de capas GEE |

Comportamiento operativo:

- El estado del job se persiste en la base de datos.
- El frontend hace polling de los endpoints de análisis/jobs para mostrar el progreso.
- Los servicios de worker corren separados del contenedor principal de la API (`worker` y `geo-worker` en Docker Compose).

## Exportación y reportes

### Reportes PDF

La plataforma genera PDFs con branding para flujos operativos y administrativos.

- Registros de tramites con seguimiento cronológico.
- Documentos de orden del día de reuniones.
- Resúmenes financieros anuales.
- Fichas técnicas o de activos adicionales según el flujo.

### Exportación geoespacial

- Exportación KMZ para Google Earth.
- Depuración automática de PII de datos sensibles antes de generar el KMZ.
- Exportaciones GeoJSON y CSV para interoperabilidad.
- Exportación de proyecto QGIS para usuarios GIS técnicos.
- Exportación de geo-bundle (un endpoint sincrónico que empaqueta capas en un ZIP descargable), con su ruta de importación correspondiente.
- Salidas orientadas a COG/VRT para flujos raster avanzados.

### Por qué la exportación importa acá

Esto no es solo software de dashboard. Los equipos de campo, los analistas GIS y los administradores necesitan salidas en formatos distintos, y el sistema lo soporta explícitamente.

## Estructura del proyecto

```text
consorcio-canalero/
|- consorcio-web/              # Frontend React
|- gee-backend/                # Backend FastAPI
|  `- app/
|     |- api/v2/               # Agregación de routers
|     |- auth/                 # JWT + OAuth
|     |- db/                   # Base, sesiones, migraciones Alembic
|     |- domains/              # Dominios de negocio (Screaming Architecture)
|     |- core/                 # Logging, rate limiting, excepciones
|     `- shared/               # Utilidades transversales
|- scripts/                    # ETLs (canales, escuelas, pilar_verde) y scripts de apoyo
|- gee/                        # Scripts de Google Earth Engine
|- martin/                     # Configuración del tile server
|- nginx/                      # Configuración del reverse proxy
|- .github/workflows/          # Pipelines de CI/CD
|- docker-compose.yml          # Stack local/dev
|- docker-compose.prod.yml     # Stack de producción
|- docker-compose.deploy.yml   # Stack específico de deploy
`- DEPLOY.md                   # Guía de despliegue
```

Docs relacionadas del repo:

- `gee-backend/README.md` para la guía específica del backend.
- `consorcio-web/README.md` para la guía específica del frontend.
- `DEPLOY.md` para detalles de infraestructura y rollout.

## Variables de entorno

Variables mínimas del backend:

```env
DATABASE_URL=postgresql://...
JWT_SECRET=...
REDIS_URL=redis://...
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
GEE_SERVICE_ACCOUNT=...
GEE_PRIVATE_KEY_PATH=/path/to/key.json
```

Variables mínimas del frontend:

```env
VITE_API_URL=http://localhost:8000
VITE_MARTIN_URL=http://localhost:3001
```

El despliegue de producción también usa URLs públicas como `MARTIN_PUBLIC_URL`, `FRONTEND_URL` y `API_BASE_URL`. Ver `DEPLOY.md` y los archivos `.env.*.example` para el setup completo del lado del servidor.

## Inicio rápido

### Script de setup recomendado

```bash
git clone https://github.com/JNZader/consorcio-canalero.git
cd consorcio-canalero
./setup.sh
```

`setup.sh` requiere Docker y Docker Compose, y crea los archivos `.env` a partir de las plantillas.

### Setup local manual

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

### Setup con Docker

```bash
docker compose up -d
docker compose up -d postgres redis
```

## Superficie de la API

Todos los endpoints actuales se agrupan bajo `/api/v2`, con docs interactivas típicamente disponibles en `/docs` y `/redoc`.

| Prefijo | Dominio | Auth |
|---------|---------|------|
| `/api/v2/auth/*` | Autenticación y perfil de usuario | Variable |
| `/api/v2/padron/*` | Registro de socios | Operador+ |
| `/api/v2/denuncias/*` | Reportes ciudadanos | Envío público, gestión Operador+ |
| `/api/v2/finanzas/*` | Flujos financieros | Operador+ |
| `/api/v2/tramites/*` | Trámites y seguimiento | Operador+ |
| `/api/v2/reuniones/*` | Reuniones y orden del día | Operador+ |
| `/api/v2/capas/*` | Gestión de capas | Operador+ |
| `/api/v2/geo/*` | Procesamiento geo y flujos GEE | Operador+ |
| `/api/v2/monitoring/*` | Sugerencias y seguimiento de análisis | Variable |
| `/api/v2/settings/*` | Settings del sistema | Operador+ lectura, Admin escritura |
| `/api/v2/public/*` | Servicios públicos de branding/visor | Sin auth |
| `/api/v2/admin/*` | Flujos de admin como invitaciones y gestión de usuarios | Admin |

## Testing

### Tests del backend

```bash
cd gee-backend && source venv/bin/activate
pytest tests/new/ -v
pytest tests/new/ -v --cov=app
ruff check .
ruff format --check .
```

Notas de testing del backend:

- `gee-backend/tests/new/` contiene los tests más nuevos, enfocados en la arquitectura.
- El patrón documentado es testing contra base real con aislamiento transaccional (vía `testcontainers`, que levanta PostgreSQL + PostGIS) en vez de mockear la persistencia.
- Hay tests de integración sobre el comportamiento del catálogo público de capas respaldado por Martin.

### Tests del frontend

```bash
cd consorcio-web
npm run test
npm run test:coverage
npm run lint
```

### E2E y chequeos de calidad

```bash
cd consorcio-web
npm run test:e2e         # config Playwright de accesibilidad
npm run test:e2e:local   # config Playwright end-to-end local
npm run mutation:run     # mutation testing con Stryker
```

Qué se cubre en la práctica:

- Vitest y Testing Library para componentes, hooks, stores y comportamiento a nivel de ruta.
- Configs y suites de Playwright bajo `consorcio-web/tests/e2e/`.
- Setup de Playwright enfocado en accesibilidad bajo `consorcio-web/tests/accessibility/`.
- Mutation testing con Stryker configurado en el repo del frontend.

## Despliegue

El repo está diseñado en torno a un modelo de despliegue separado.

### Deploy del frontend

Cloudflare Pages sirve la aplicación React.

- Directorio raíz: `consorcio-web`
- Comando de build: `npm run build`
- Directorio de salida: `dist`
- Las variables de entorno incluyen `VITE_API_URL` y, cuando aplica, `VITE_MARTIN_URL`
- `_headers` y `_redirects` dan soporte al ruteo SPA y a la política de seguridad/cache

### Deploy del backend y servicios

Los servicios en Hetzner corren el stack operativo del backend.

- Servicio de API FastAPI.
- PostgreSQL + PostGIS.
- Redis.
- Worker de Celery y geo worker.
- Martin tile server.

Las docs de producción también hacen referencia a imágenes GHCR y al rollout mediante Docker Compose en el servidor.

### Nota operativa

El frontend y el backend están desacoplados a propósito, así la web app pública puede desplegarse rápido mientras los datos, los tiles y los servicios de worker quedan bajo una infraestructura controlada.

## Notas de CI/CD

El repositorio incluye workflows de GitHub Actions para backend, frontend, deploy, GitHub Pages, Fly y CodeQL (`.github/workflows/`).

A alto nivel:

- Los pushes al frontend pueden disparar builds de Cloudflare Pages automáticamente.
- Los cambios en el backend corren chequeos de CI y pueden construir/publicar imágenes de contenedor.
- El rollout de producción está documentado en `DEPLOY.md`, incluyendo actualizaciones opcionales del servidor por webhook.
- El primer camino de build documentado en `DEPLOY.md` publica las imágenes de backend y geo-worker en GHCR.

## Licencia

Licencia MIT. Ver [LICENSE](LICENSE).

Construido para el **Consorcio Canalero 10 de Mayo** en Bell Ville, Córdoba, Argentina.
</content>
</invoke>
