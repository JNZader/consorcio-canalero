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
| `ENABLE_PRODUCTION_DEPLOY` | `true` únicamente cuando quieras habilitar el rollout automático; dejala sin definir o en `false` por defecto |
| `DEPLOY_WEBHOOK_URL` | URL del webhook del server (ver paso 3.4); por sí sola no habilita el deploy |

### 1.3 Secret del webhook (environment `production`, no secret de repositorio)

Creá el environment **antes** de poner `ENABLE_PRODUCTION_DEPLOY=true`. Si no existe, GitHub lo crea vacío en el primer deploy y no pide aprobación. Los pasos del panel están en [`docs/runbooks/infra-cicd-v6.md`](docs/runbooks/infra-cicd-v6.md).

| Dónde | Nombre | Valor |
|-------|--------|-------|
| Environment `production` → Secrets | `DEPLOY_WEBHOOK_SECRET` | Token de 32 caracteres o más, el mismo que `/etc/consorcio/deploy-webhook.env` en el server |
| Environment `production` → Protection rules | Required reviewers | Quien aprueba un deploy a Hetzner |
| Environment `production` → Deployment branches | `main` | Solo esa rama |

Borrá el secret de repositorio con el mismo nombre si todavía está: un job sin este environment no tiene que verlo. `ENABLE_PRODUCTION_DEPLOY` sigue siendo variable de repositorio y apaga el job aunque el environment exista.

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

> La rama de producción de Pages tiene que ser `pages-production`, no `main`.
> El workflow `pages.yml` adelanta esa rama solo cuando Frontend CI termina en
> verde en un push a `main`. Hasta cambiar el panel, Cloudflare sigue publicando
> `main` sin esperar al CI. El cambio es manual y está en
> [`docs/runbooks/infra-cicd-v6.md`](docs/runbooks/infra-cicd-v6.md): esperá a
> que `pages-production` exista y después, en Workers & Pages → el proyecto →
> Settings → Builds & deployments, poné Production branch = `pages-production`.

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
POSTGRES_HOST=shared-postgres
POSTGRES_USER=consorcio
POSTGRES_PASSWORD=PASSWORD_APP_REAL
POSTGRES_DB=consorcio_canalero
USE_PGBOUNCER=false
DATABASE_URL=postgresql://consorcio:PASSWORD_APP_REAL@shared-postgres:5432/consorcio_canalero
APP_DATABASE_URL=postgresql://consorcio_app:PASSWORD_APP_RW@shared-postgres:5432/consorcio_canalero
REDIS_URL=redis://:PASSWORD_REDIS_REAL@shared-redis:6379/0
JWT_SECRET=<output de: openssl rand -hex 32>
CORS_ORIGINS=https://consorcio.TUDOMINIO,https://consorcio-canalero.pages.dev
MARTIN_PUBLIC_URL=https://tiles.consorcio.TUDOMINIO
MARTIN_DB_URL=postgresql://consorcio_martin:PASSWORD_MARTIN_INDEPENDIENTE@shared-postgres:5432/consorcio_canalero
FRONTEND_URL=https://consorcio.TUDOMINIO
API_BASE_URL=https://api.consorcio.TUDOMINIO
```

> `DATABASE_URL` es el migrador (`consorcio`, superuser de la imagen).
> Runtime (`backend` / workers) usa `APP_DATABASE_URL` con `consorcio_app`
> (DB-04, sin SUPERUSER). `MARTIN_DB_URL` usa `consorcio_martin`.
> Ver [`docs/APP_DB_ROLE.md`](docs/APP_DB_ROLE.md). Usá URLs canónicas
> `postgresql://`; la aplicación deriva internamente el driver async.

Martin recibe `SELECT` solo sobre `vt_caminos_unificados`, `vt_zonas_operativas`, `vt_puntos_conflicto`,
`vt_canal_network` y `vt_parcelas_catastro`. No recibe tablas base, escritura, secuencias
ni funciones de aplicación. El procedimiento y sus chequeos están en
[`docs/MARTIN_DB_ROLE.md`](docs/MARTIN_DB_ROLE.md).

### 3.4 Migrar, provisionar Martin y levantar el stack

Aplicá primero las migraciones, antes de crear o reparar los permisos del lector:

~~~bash
cd /home/javier/stacks/consorcio
docker compose pull backend
docker compose run --rm migrate
~~~

Después seguí [`docs/MARTIN_DB_ROLE.md`](docs/MARTIN_DB_ROLE.md) para ejecutar
`scripts/provision_martin_reader.sql` contra `shared-postgres` y establecer la
contraseña con `\password consorcio_martin` dentro de una sesión interactiva de
`psql`. Nunca pongas la contraseña real en argumentos del shell.

Cuando la migración, el aprovisionamiento y sus cuatro contadores en cero hayan
terminado:

~~~bash
cd /home/javier/stacks/consorcio
docker compose up -d

# Verificar que todo arrancó
docker compose ps

# Verificar endpoints
curl -s http://localhost:8000/health
curl -s http://localhost:3000/health
curl -s http://localhost:8001/health
~~~

### 3.5 Instalar el Caddyfile versionado

La fuente es [`deploy/Caddyfile`](deploy/Caddyfile) (encode, HSTS con `preload`,
sin `Server`/`Via`/`X-XSS-Protection`, body máximo 20 MB, logs JSON). No uses
`deploy/Caddyfile.with-ratelimit` en el Caddy stock: `rate_limit` exige un
binario con el módulo `caddy-ratelimit`.

```bash
cp /home/javier/caddy/Caddyfile /home/javier/caddy/Caddyfile.bak.$(date -u +%Y%m%d)
# Ajustá los hosts vivos (cc10demayo-api / cc10demayo-tiles) o DOMAIN.
caddy validate --config /home/javier/caddy/Caddyfile
caddy reload --config /home/javier/caddy/Caddyfile
```

El procedimiento completo, el rate limit y la advertencia de no enviar el
dominio a hstspreload.org están en [`docs/runbooks/infra-cicd-v6.md`](docs/runbooks/infra-cicd-v6.md).

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

## Deploys futuros

Cada `git push origin main` que toque `gee-backend/**` o
`.github/workflows/deploy.yml`:

1. GitHub Actions corre el quality gate completo.
2. Si pasa, buildea y publica las imágenes de backend y geo-worker en GHCR.
3. Solo llama al webhook si `ENABLE_PRODUCTION_DEPLOY=true` **y**
   `DEPLOY_WEBHOOK_URL` está configurada.

El workflow de publicación es deliberadamente push-only: ni los pull requests ni
`workflow_dispatch` pueden publicar imágenes. Para habilitar el rollout
automático: instalá el receptor (`deploy/deploy_webhook.py`, pasos en el
runbook), cargá `DEPLOY_WEBHOOK_URL` como variable de repositorio, creá el
environment `production` con un revisor y el secret `DEPLOY_WEBHOOK_SECRET`,
y recién entonces establecé `ENABLE_PRODUCTION_DEPLOY=true`. El job declara
`environment: production`, así que con el kill switch prendido igual espera
esa aprobación. Una URL existente, sin ese opt-in, deja el job deshabilitado.

Para el frontend, Cloudflare Pages tiene que publicar la rama `pages-production`.
El workflow `frontend.yml` ejecuta el gate completo en pull requests a `main` y
en ejecuciones manuales, incluida la matriz de accesibilidad Chromium/Firefox/WebKit.
`pages.yml` adelanta `pages-production` solo después de ese gate en un push a `main`.
