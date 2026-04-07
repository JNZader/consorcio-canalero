# Deploy — Consorcio Canalero

Arquitectura: **Cloudflare Pages** (frontend) + **Hetzner CX33** (backend, geo-worker, Martin, Celery).

---

## 1. GitHub — una sola vez

### 1.1 Hacer los packages de GHCR públicos

Después del primer push a `main`, van a aparecer los packages en tu perfil de GitHub.  
Andá a `github.com/JNZader/consorcio-canalero` → **Packages** → para cada imagen (`backend`, `geo-worker`):  
→ **Package settings** → **Change visibility** → **Public**

Si los dejás privados, el server va a necesitar `docker login ghcr.io` con un token antes de hacer `pull`.

### 1.2 Repository Variables (Settings → Secrets and variables → Actions → Variables)

| Variable | Valor |
|----------|-------|
| `DEPLOY_WEBHOOK_URL` | URL del webhook del server (ver paso 3.4) — podés dejarlo vacío por ahora |

### 1.3 Repository Secrets (Settings → Secrets and variables → Actions → Secrets)

| Secret | Valor |
|--------|-------|
| `DEPLOY_WEBHOOK_SECRET` | Token que elegís vos para el webhook (cualquier string largo) |

### 1.4 Disparar el primer build

```bash
git push origin main
```

Esto buildea y pushea a GHCR:
- `ghcr.io/jnzader/consorcio-canalero/backend:latest`
- `ghcr.io/jnzader/consorcio-canalero/geo-worker:latest`

Verificá en la pestaña **Actions** que los dos jobs terminen en verde. El geo-worker tarda ~20 min la primera vez (WhiteboxTools).

---

## 2. Cloudflare Pages — una sola vez

1. Entrá a **dash.cloudflare.com** → Workers & Pages → **Create application** → **Pages** → **Connect to Git**
2. Seleccioná el repo `JNZader/consorcio-canalero`
3. Configuración del build:
   - **Framework preset**: Vite
   - **Build command**: `npm run build`
   - **Build output directory**: `dist`
   - **Root directory**: `consorcio-web`
4. **Environment variables** (pestaña de settings después de crear el proyecto):

   | Variable | Valor |
   |----------|-------|
   | `VITE_API_URL` | `https://api.consorcio.TUDOMINIO` |
   | `VITE_MARTIN_URL` | `https://tiles.consorcio.TUDOMINIO` |

5. **Custom domain**: configurá `consorcio.TUDOMINIO` en la pestaña Domains.

> CF Pages buildea automáticamente en cada push a `main`. No necesitás hacer nada más acá.

---

## 3. Servidor Hetzner — una sola vez

### 3.1 Seguir la guía hasta Fase 3 inclusive

Tenés que tener corriendo en el server:
- Caddy (proxy), Dockge, Dozzle, Uptime Kuma
- `shared-postgres` con la base `consorcio_canalero` ya creada
- `shared-redis`

Verificá que la base existe:
```bash
docker exec shared-postgres psql -U postgres -c "\l" | grep consorcio
```

### 3.2 Copiar los archivos del stack

```bash
mkdir -p /home/javier/stacks/consorcio
cd /home/javier/programacion/consorcio-canalero  # o cloná el repo en el server

cp docker-compose.prod.yml /home/javier/stacks/consorcio/docker-compose.yml
cp martin/config.prod.yaml /home/javier/stacks/consorcio/martin-config.yaml
cp .env.prod.example       /home/javier/stacks/consorcio/.env
```

### 3.3 Completar el .env

```bash
nano /home/javier/stacks/consorcio/.env
```

Reemplazá TODOS los `CAMBIAR_*` y `TUDOMINIO`:

```env
DATABASE_URL=postgresql+asyncpg://consorcio:PASSWORD_REAL@shared-postgres:5432/consorcio_canalero
REDIS_URL=redis://:PASSWORD_REDIS_REAL@shared-redis:6379/0
JWT_SECRET=<output de: openssl rand -hex 32>
CORS_ORIGINS=https://consorcio.TUDOMINIO,https://consorcio-canalero.pages.dev
MARTIN_PUBLIC_URL=https://tiles.consorcio.TUDOMINIO
MARTIN_DB_URL=postgresql://consorcio:PASSWORD_REAL@shared-postgres:5432/consorcio_canalero
FRONTEND_URL=https://consorcio.TUDOMINIO
API_BASE_URL=https://api.consorcio.TUDOMINIO
```

> El password de consorcio en shared-postgres es el que pusiste en el `init-databases.sh` de la Fase 3.

### 3.4 Levantar el stack

```bash
cd /home/javier/stacks/consorcio
docker compose up -d

# Verificar que todo arrancó
docker compose ps

# Verificar que Alembic corrió las migraciones
docker logs consorcio-backend --tail 50 | grep -i migrat

# Verificar endpoints
curl -s http://localhost:8000/health
curl -s http://localhost:3000/health
curl -s http://localhost:8001/health
```

### 3.5 Agregar las entradas al Caddyfile del server

```bash
nano /home/javier/caddy/Caddyfile
```

Agregá al final (antes del `CADDYEOF` si seguiste la guía):

```caddy
# --- Consorcio API ---
api.consorcio.{$DOMAIN} {
    reverse_proxy consorcio-backend:8000
}

# --- Consorcio Tiles (Martin) ---
tiles.consorcio.{$DOMAIN} {
    reverse_proxy consorcio-martin:3000
}
```

Recargá Caddy:
```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
docker logs caddy --tail 10
```

---

## 4. DNS — una sola vez

En tu proveedor de DNS, apuntá estos registros a la IP del server Hetzner:

| Tipo | Nombre | Valor |
|------|--------|-------|
| A | `api.consorcio` | `IP_DEL_SERVER` |
| A | `tiles.consorcio` | `IP_DEL_SERVER` |

El registro `consorcio` ya lo maneja Cloudflare Pages automáticamente.

---

## 5. Verificación final

```bash
# Desde cualquier lado
curl -s https://api.consorcio.TUDOMINIO/health
curl -s https://tiles.consorcio.TUDOMINIO/health
curl -s https://tiles.consorcio.TUDOMINIO/catalog | head -20
```

Y abrí `https://consorcio.TUDOMINIO` en el browser.

---

## Deploys futuros (automático)

Cada `git push origin main` que toque `gee-backend/**`:
1. GitHub Actions corre lint + tests
2. Buildea y pushea las imágenes a GHCR
3. (Opcional) Llama al webhook del server → `docker compose pull && docker compose up -d`

Para activar el auto-deploy via webhook, configurá el servidor webhook de la Fase 2 de la guía y completá `DEPLOY_WEBHOOK_URL` en las Repository Variables de GitHub.

Para el frontend, cada `git push` dispara un nuevo deploy en Cloudflare Pages automáticamente.
