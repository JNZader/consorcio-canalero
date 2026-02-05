# Consorcio Canalero 10 de Mayo

Sistema integral de gestión para el Consorcio Canalero 10 de Mayo - Bell Ville, Córdoba, Argentina.

[![CI/CD Pipeline](https://github.com/YOUR_USERNAME/consorcio-canalero/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/consorcio-canalero/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Características Principales

### Monitoreo Satelital e Inteligencia Espacial
- **Detección de Inundaciones**: Análisis automático usando Sentinel-1 (Radar) y Sentinel-2 (Óptico)
- **Intersecciones Inteligentes**: Cálculo automático de cruces entre caminos y canales
- **Puntos de Interés (POI)**: Marcación manual en mapa para registro de activos

### Gestión de Infraestructura y Activos
- **Bitácora de Mantenimiento**: Registro de reparaciones, limpiezas y obras con fotos y costos
- **Fichas Técnicas**: Generación de PDFs técnicos para cada activo

### Administración y Padrón
- **Padrón de Consorcistas**: Registro con validación de CUIT y gestión de representación
- **Recaudación**: Control de pago de cuotas anuales con historial
- **Gestión de Trámites**: Seguimiento de expedientes ante Recursos Hídricos

### Sistema de Reportes y Sugerencias
- **Reportes Ciudadanos**: Denuncias con verificación de identidad
- **Buzón de Sugerencias**: Propuestas para reuniones de comisión
- **Planificación de Reuniones**: Constructor de Orden del Día

## Tech Stack

| Componente | Tecnología |
|------------|------------|
| **Frontend** | React 19, TypeScript, Vite, Mantine UI, Leaflet |
| **Backend** | FastAPI, Python 3.11, Google Earth Engine |
| **Base de datos** | Supabase (PostgreSQL) |
| **Cache/Queue** | Redis, Celery |
| **Infraestructura** | Docker, Nginx, GitHub Actions |
| **Hosting** | Koyeb |

## Estructura del Proyecto

```
consorcio-canalero/
├── consorcio-web/          # Frontend React
│   ├── src/
│   │   ├── components/     # Componentes React
│   │   ├── hooks/          # Custom hooks
│   │   ├── lib/            # Utilidades y API
│   │   ├── stores/         # Estado global (Zustand)
│   │   └── types/          # TypeScript types
│   └── Dockerfile
├── gee-backend/            # Backend FastAPI
│   ├── app/
│   │   ├── api/v1/         # Endpoints REST
│   │   ├── services/       # Lógica de negocio
│   │   └── core/           # Configuración
│   └── Dockerfile
├── nginx/                  # Configuración Nginx
├── .github/workflows/      # CI/CD pipelines
├── docker-compose.yml      # Desarrollo
└── docker-compose.prod.yml # Producción
```

## Requisitos

- Node.js >= 20
- Python >= 3.11
- Docker & Docker Compose
- Make (opcional)

## Inicio Rápido

### 1. Clonar y configurar

```bash
git clone https://github.com/YOUR_USERNAME/consorcio-canalero.git
cd consorcio-canalero

# Copiar archivos de configuración
cp gee-backend/.env.example gee-backend/.env
cp consorcio-web/.env.example consorcio-web/.env
```

### 2. Configurar credenciales

**Backend (`gee-backend/.env`):**
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-anon-key
SUPABASE_SECRET_KEY=your-service-role-key
GEE_KEY_FILE_PATH=/app/credentials/gee-service-account.json
GEE_PROJECT_ID=cc10demayo
```

**Frontend (`consorcio-web/.env`):**
```env
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### 3. Desarrollo con Docker (Recomendado)

```bash
# Iniciar todos los servicios
make dev
# o
docker compose up -d

# Ver logs
docker compose logs -f

# Detener
docker compose down
```

**Servicios disponibles:**
- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 4. Desarrollo local (sin Docker)

```bash
# Setup completo
make setup

# Backend (terminal 1)
cd gee-backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (terminal 2)
cd consorcio-web
npm install
npm run dev
```

## Comandos Disponibles

```bash
# Desarrollo
make dev              # Iniciar todos los servicios
make logs             # Ver logs
make stop             # Detener servicios

# Testing
make test             # Ejecutar todos los tests
make test-frontend    # Solo tests del frontend
make test-backend     # Solo tests del backend

# Linting
make lint             # Lint todo
make lint-fix         # Auto-fix linting

# Docker
make docker-build     # Construir imágenes
make docker-prod      # Ejecutar en modo producción

# Limpieza
make clean            # Limpiar artefactos
```

## CI/CD Pipeline

El pipeline se ejecuta automáticamente en cada push:

```
┌─────────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐     ┌────────┐
│   Detect    │────▶│   Test   │────▶│ Security │────▶│  Build  │────▶│ Deploy │
│   Changes   │     │ & Lint   │     │   Scan   │     │  Images │     │ Koyeb  │
└─────────────┘     └──────────┘     └──────────┘     └─────────┘     └────────┘
```

### GitHub Secrets Requeridos

| Secret | Descripción |
|--------|-------------|
| `KOYEB_TOKEN` | Token de API de Koyeb |
| `VITE_SUPABASE_URL` | URL de Supabase |
| `VITE_SUPABASE_ANON_KEY` | Anon key de Supabase |

### GitHub Variables

| Variable | Descripción |
|----------|-------------|
| `VITE_API_URL` | URL del backend en producción |
| `BACKEND_URL` | URL para health checks |

## Producción

```bash
# Crear archivo de producción
cp gee-backend/.env.production.example gee-backend/.env.production
# Editar con valores de producción

# Ejecutar
docker compose -f docker-compose.prod.yml up -d
```

### Arquitectura en Producción

```
                    ┌──────────────┐
                    │   Internet   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    Nginx     │ :80/:443
                    │  (Frontend)  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐     │     ┌──────▼──────┐
       │   Static    │     │     │    /api/*   │
       │   Assets    │     │     │    Proxy    │
       └─────────────┘     │     └──────┬──────┘
                           │            │
                    ┌──────▼───────┐    │
                    │   Backend    │◀───┘
                    │   FastAPI    │ :8000
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌───▼────┐ ┌─────▼─────┐
       │   Supabase  │ │  GEE   │ │   Redis   │
       │  PostgreSQL │ │  API   │ │   Cache   │
       └─────────────┘ └────────┘ └─────┬─────┘
                                        │
                                 ┌──────▼──────┐
                                 │   Celery    │
                                 │   Worker    │
                                 └─────────────┘
```

## Informes PDF

El sistema genera 5 tipos de documentos:
1. Informe de Gestión Integral
2. Ficha Técnica de Activo
3. Resumen de Expediente Provincial
4. Constancia de Resolución de Reporte
5. Orden del Día para Reuniones

## Endpoints Principales

| Endpoint | Descripción |
|----------|-------------|
| `/health` | Health check |
| `/api/v1/reports` | Gestión de reportes |
| `/api/v1/sugerencias` | Buzón de sugerencias |
| `/api/v1/monitoring` | Dashboard de monitoreo |
| `/api/v1/layers` | Capas del mapa |
| `/api/v1/gee_layers` | Capas de Google Earth Engine |
| `/docs` | Documentación OpenAPI |

## Contribuir

1. Fork el repositorio
2. Crear branch (`git checkout -b feature/nueva-funcionalidad`)
3. Commit (`git commit -m 'Agregar nueva funcionalidad'`)
4. Push (`git push origin feature/nueva-funcionalidad`)
5. Abrir Pull Request

### Pre-commit Hooks

```bash
pip install pre-commit
pre-commit install
```

## Licencia

MIT License - ver [LICENSE](LICENSE) para detalles.

---

Desarrollado para el **Consorcio Canalero 10 de Mayo** - Bell Ville, Córdoba, Argentina
