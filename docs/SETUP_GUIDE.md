# Guía de setup — Consorcio Canalero

Guía rápida para levantar el entorno local actual.

## Requisitos

- Docker / Docker Compose
- Node.js 20+
- Python 3.11+
- PostgreSQL + PostGIS si se corre sin Docker
- Redis si se corre sin Docker
- Credenciales de Google Earth Engine para funciones geoespaciales avanzadas

## Opción recomendada: Docker

Desde la raíz del repo:

```bash
cp gee-backend/.env.example gee-backend/.env
# editar JWT_SECRET, REDIS_URL, DATABASE_URL y credenciales GEE si corresponde

docker compose up -d
```

Servicios principales:

- Backend FastAPI: `http://localhost:8000`
- Docs OpenAPI: `http://localhost:8000/docs`
- Frontend Vite: `http://localhost:5173` si se levanta aparte con npm
- Martin tiles: interno al stack Docker
- PostgreSQL/PostGIS y Redis: servicios del compose

## Backend local sin Docker

```bash
cd gee-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# editar .env
alembic upgrade head
uvicorn app.main:app --reload
```

Variables mínimas:

```env
DATABASE_URL=postgresql://consorcio:consorcio_dev@localhost:5432/consorcio
JWT_SECRET=<openssl rand -hex 32>
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
FRONTEND_URL=http://localhost:5173
API_PREFIX=/api/v2
```

## Frontend local

```bash
cd consorcio-web
npm install
cp .env.example .env
npm run dev
```

Variables mínimas:

```env
VITE_API_URL=http://localhost:8000
VITE_MARTIN_URL=http://localhost:3001
```

## Verificación rápida

```bash
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

En el navegador:

- `http://localhost:5173`
- `http://localhost:5173/mapa`
- `http://localhost:5173/login`

## Tests

Backend:

```bash
cd gee-backend
source venv/bin/activate
pytest tests/new/ -v
ruff check .
ruff format --check .
```

Frontend:

```bash
cd consorcio-web
npm run lint
npm run typecheck
npm run test:run
```
