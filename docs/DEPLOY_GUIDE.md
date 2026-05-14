# Guía de despliegue — Consorcio Canalero

La topología actual separa frontend público y servicios backend.

- Frontend: Cloudflare Pages desde `consorcio-web/`
- Backend/API: Docker Compose en Hetzner
- Datos: PostgreSQL + PostGIS
- Jobs: Celery + Redis
- Tiles: Martin
- Imágenes backend: GHCR

Para el flujo operativo completo usar `DEPLOY.md` como fuente principal.

## Frontend — Cloudflare Pages

Configuración del proyecto:

| Setting | Valor |
|---------|-------|
| Framework preset | Vite |
| Root directory | `consorcio-web` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node version | 20+ |

Variables:

```env
VITE_API_URL=https://api.consorcio.DOMINIO
VITE_MARTIN_URL=https://tiles.consorcio.DOMINIO
```

Cada push a `main` puede disparar un build automático de Pages.

## Backend — Hetzner / Docker Compose

Archivos principales:

- `docker-compose.prod.yml`
- `.env.prod.example`
- `martin/config.prod.yaml`
- `DEPLOY.md`

Preparación en el servidor:

```bash
mkdir -p /home/javier/stacks/consorcio
cd /home/javier/programacion/consorcio-canalero

cp docker-compose.prod.yml /home/javier/stacks/consorcio/docker-compose.yml
cp martin/config.prod.yaml /home/javier/stacks/consorcio/martin-config.yaml
cp .env.prod.example /home/javier/stacks/consorcio/.env
```

Editar `/home/javier/stacks/consorcio/.env` con valores reales:

```env
DATABASE_URL=postgresql+asyncpg://consorcio:PASSWORD@shared-postgres:5432/consorcio_canalero
MARTIN_DB_URL=postgresql://consorcio:PASSWORD@shared-postgres:5432/consorcio_canalero
REDIS_URL=redis://:PASSWORD@shared-redis:6379/0
JWT_SECRET=<openssl rand -hex 32>
CORS_ORIGINS=https://consorcio.DOMINIO,https://consorcio-canalero.pages.dev
FRONTEND_URL=https://consorcio.DOMINIO
API_BASE_URL=https://api.consorcio.DOMINIO
MARTIN_PUBLIC_URL=https://tiles.consorcio.DOMINIO
```

Levantar stack:

```bash
cd /home/javier/stacks/consorcio
docker compose up -d
docker compose ps
```

## Proxy y DNS

Caddy debe enrutar:

```caddy
api.consorcio.{$DOMAIN} {
    reverse_proxy consorcio-backend:8000
}

tiles.consorcio.{$DOMAIN} {
    reverse_proxy consorcio-martin:3000
}
```

DNS:

| Tipo | Nombre | Destino |
|------|--------|---------|
| A | `api.consorcio` | IP del servidor |
| A | `tiles.consorcio` | IP del servidor |

## Verificación

```bash
curl -s https://api.consorcio.DOMINIO/health
curl -s https://tiles.consorcio.DOMINIO/health
curl -s https://tiles.consorcio.DOMINIO/catalog | head -20
```

Luego abrir:

```text
https://consorcio.DOMINIO
```
