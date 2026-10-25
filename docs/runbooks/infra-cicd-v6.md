# Runbook — infraestructura y CI (auditoría v6)

Pasos que no pueden quedar solo en el repo: hay que hacerlos en el VPS, en
GitHub o en Cloudflare. El código de este cambio no los ejecuta.

Fuente de verdad del stack en Hetzner: **`docker-compose.prod.yml`** (imágenes
GHCR por digest, Postgres y Redis externos). `docker-compose.deploy.yml` está
**deprecado** (INF-07): ningún workflow lo usa. Sigue en el repo, marcado
`DEPRECATED`, solo para que una copia vieja en el VPS no pierda `cap_drop` si
alguien la sincroniza antes del corte de abajo. No instalarlo en un server nuevo.

## RTO / RPO (INF-05)

Un solo VPS Hetzner (CX33). No hay segundo sitio.

| Objetivo | Valor | De dónde sale |
|---|---|---|
| RPO | 24 h | Backup diario a las 03:20. Si el último éxito tiene más de 26 h, el timer de frescura falla. |
| RTO | 4 h | Tiempo objetivo del simulacro de restore, de máquina nueva a API respondiendo `/live`. |

### Reconstruir el VPS desde cero

1. Crear otro CX33, instalar Docker y Caddy. No abrir Postgres ni Redis a internet.
2. Restaurar el dump más reciente en una base nueva (sección Restore). No reutilizar el volumen viejo si no se verificó.
3. Restaurar los volúmenes `consorcio-geo-data` y `consorcio-denuncia-uploads` con restic (RUNBOOK §3.6).
4. Copiar al server `docker-compose.prod.yml`, `martin/config.prod.yaml`, `deploy/Caddyfile` y un `.env` nuevo. Los secretos salen del gestor de contraseñas, no del backup en claro.
5. Pinchar `BACKEND_DIGEST` y `GEO_WORKER_DIGEST` con el último `deploy-digests.env` o con el digest que publicó Actions.
6. `docker compose up -d` y comprobar `/live`, `/ready` y el `/health` de Martin.
7. Apuntar los A de `cc10demayo-api` y `cc10demayo-tiles` a la IP nueva. El frontend sigue en Cloudflare Pages y no vive en el VPS.

## Qué compose corre en Hetzner (INF-07)

Hoy el runbook histórico describe un `docker-compose.yml` del server que se
parece a `docker-compose.deploy.yml` (build local, Postgres y Redis en el
mismo compose). **El único archivo que se instala es `docker-compose.prod.yml`.**
`docker-compose.deploy.yml` está deprecado y no es un camino de deploy.

Corte, en una ventana con backup fresco:

1. Confirmar que GHCR tiene los dos digests que va a usar el `.env`.
2. Backup (sección de abajo) y comprobar el stamp.
3. Reemplazar `/home/javier/stacks/consorcio/docker-compose.yml` por `docker-compose.prod.yml`.
4. Postgres y Redis pasan a ser los servicios externos (`shared-postgres`, `shared-redis`) que ya documenta `DEPLOY.md`. Si el server todavía usa el Postgres embebido, hacer antes el upgrade de la sección DB-05 y dejar ese contenedor en la red `backend` con el nombre que espera `POSTGRES_HOST`.
5. `docker compose up -d`. No hace falta `--build`.

Hasta ese corte el server puede tener una copia vieja. No la actualices desde
`docker-compose.deploy.yml`: hacé el corte. El archivo del repo queda deprecado
para no borrar de un golpe la referencia que el VPS todavía puede tener en disco.

## Contenedores (INF-08)

Cada servicio de los dos compose de producción tiene:

- `security_opt: [no-new-privileges:true]`
- `cap_drop: [ALL]`
- logs `json-file` (10m × 3), heredados del ancla o repetidos en el servicio

Postgres, Redis y PgBouncer arrancan como root y bajan de usuario en el
entrypoint. Necesitan `cap_add`: `CHOWN`, `DAC_OVERRIDE`, `FOWNER`, `SETGID`,
`SETUID`. Los init que hacen `chown` (`uploads-init`, `celery-beat-init`)
agregan solo `CHOWN`, `DAC_OVERRIDE` y `FOWNER`.

`read_only` + `tmpfs` en `/tmp` está en backend, migrate, celery-worker,
celery-beat y Martin. No está en:

- geo-worker: supervisord escribe el pid y el log, y WhiteboxTools escribe al lado del binario.
- Postgres, Redis y PgBouncer: el entrypoint escribe fuera del volumen de datos (socket, config generada, ajuste de dueños).
- backups: restic y el CLI de B2 escriben en el home.

Si un contenedor entra en restart loop justo después de este cambio, el primer
dato es `docker logs`. Quitar solo el `read_only` de ese servicio es el
rollback; no hace falta devolverle capabilities de más.

## Imágenes por digest (INF-03, INF-11, INF-12, DB-05)

| Imagen | Pin |
|---|---|
| Redis | `redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499` |
| Martin | `ghcr.io/maplibre/martin:1.16.1@sha256:59902019bf9038926ff0c71174237d6852e64c457830a6349abe7090be8818ca` |
| PgBouncer | `edoburu/pgbouncer:v1.26.0-p0@sha256:b17551c776ef7e5769ef80b956d20f85e2fd25dd8912d31d58f782aad495b711` |
| Node (build del frontend) | `node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402` |
| Backup | `alpine:3.22@sha256:5291449c3df73caf6ed85e649dec1b9e818b39a5d8c871e97afc13e9cd5e8fa8` |
| Postgres embebido | `pgrouting/pgrouting:16-3.5-3.8@sha256:4c480c7f9e25a3490573cd6ef86b286fd21162e288cc355e8da2b52518ef6ab8` |

Martin estable es **1.16.1** (el tag de la imagen no lleva `v`; `latest` apunta
al mismo digest `sha256:59902019bf90…`). 2.0.0-beta no es estable: deja de leer
`DATABASE_URL` y exige PostGIS 3.5. La 1.0 no cambia el formato respecto de
0.20; el config de este repo (`connection_string`, `auto_publish: false`,
`tables`) es el esquema que documenta 1.16. Los YAML de `martin/` y
`martin-config.deploy.yaml` validan contra `schemas/config.json` del tag
`martin-v1.16.1`. `/catalog` sigue publicando las fuentes bajo la clave
`tiles`. El contenedor trae `wget` y `/health`, que es lo que usa el
healthcheck. Martin no tiene volumen de datos.

En el VPS, después de tener el compose nuevo: `docker compose pull martin` y
`docker compose up -d martin`. Si `/health` no pasa, el rollback es volver el
pin anterior `v0.14.2@sha256:2326005041…` en una ventana con backup.

El Dockerfile de pgvector de desarrollo (`docker/postgres/Dockerfile`) FROMs
exactamente la misma imagen pineada que el compose
(`pgrouting/pgrouting:16-3.5-3.8@sha256:4c480c7f…`); el paquete
`postgresql-16-pgvector=0.8.6-1.pgdg11+1` se sirve desde
`apt-archive.postgresql.org` (PGDG retiró `bullseye-pgdg` del repositorio
normal al terminar el LTS de Debian 11, 2026-08-31). La igualdad
overlay↔compose la pinnea `tests/test_infra_v6_contracts.py`. Sigue sin
ser la imagen de producción (solo `make rag-db` / `test-rag`).

### Upgrade de Postgres / pgRouting (DB-05)

La imagen vieja `16-3.4-3.6.1` trae PostgreSQL 16.2 (febrero 2024). La imagen
nueva es el tag upstream `16-3.5-3.8` (PostgreSQL 16, PostGIS 3.5, pgRouting
3.8, publicada el 2026-09-04). Un salto de minor dentro de 16 no necesita
`pg_upgrade` ni dump. El salto a 17 sí, y no es este cambio.

En el server, **después** de un backup verificado y **antes** de recrear el
contenedor:

1. Anotar `SELECT version();` y `SELECT extname, extversion FROM pg_extension;`.
2. Recrear solo el servicio postgres con la imagen pinneada.
3. Cuando acepte conexiones:

   ```sql
   ALTER EXTENSION postgis UPDATE;
   ALTER EXTENSION pgrouting UPDATE;
   ```

4. Volver a correr las dos consultas. Tiene que decir PostgreSQL 16.x con x
   distinto de 2, PostGIS 3.5 y pgRouting 3.8.
5. `alembic upgrade head` contra esa base (el servicio `migrate`).

Si Postgres es el `shared-postgres` de fuera del compose, el mismo procedimiento
se aplica a esa imagen, no a un servicio de `docker-compose.prod.yml` (ahí
Postgres no está). El gate de `deploy.yml` ya levanta la imagen nueva vacía
para las migraciones.

### Postgres 17 + pgRouting 4.0 (no aplicado)

El pin de deploy, de desarrollo y de CI sigue en
`pgrouting/pgrouting:16-3.5-3.8@sha256:4c480c7f9e25a3490573cd6ef86b286fd21162e288cc355e8da2b52518ef6ab8`
(PostgreSQL 16, PostGIS 3.5, pgRouting 3.8). La imagen upstream
`pgrouting/pgrouting:17-3.5-4.0` existe
(`sha256:6d9953bfbebf31b32cd6d9d87691d093d4eb1cf35b5b4e6f8cf87e3a2f29b49c`,
linux/amd64). No se cambia el pin: un directorio de datos de PostgreSQL 16
no arranca con un binario 17. En desarrollo el volumen nombrado del compose
es el mismo caso; en CI los tests usan `postgis/postgis:16-3.4` vacío, pero
el gate de migraciones de `deploy.yml` y el Postgres embebido del server
comparten el pin de producción. El Dockerfile de pgvector
(`docker/postgres/Dockerfile`) FROMs ese mismo pin (ver arriba); el
paquete `postgresql-16-pgvector=0.8.6-1.pgdg11+1` llega desde el archivo
congelado de PGDG.

Hay también `pgrouting/pgrouting:16-3.5-4.0` (mismo major de Postgres,
pgRouting 4.0). Eso tampoco se aplica acá: `ALTER EXTENSION pgrouting UPDATE`
a 4.0 cambia firmas SQL y hay que medirlo contra las funciones de ruteo, no
esconderlo en un bump de digest.

Ventana, con backup verificado y el server en mantenimiento:

**Dump / restore** (el camino si no hay binarios de las dos majors en el
mismo contenedor):

1. `SELECT version();` y `SELECT extname, extversion FROM pg_extension;`.
2. Desde la imagen de backup (cliente 16, `scripts/Dockerfile.backup`):
   `pg_dump -Fc -d "$DATABASE_URL" -f consorcio-16.dump`.
3. Levantar un contenedor nuevo con
   `pgrouting/pgrouting:17-3.5-4.0` y un volumen vacío. No reutilizar el
   PGDATA de la 16.
4. `pg_restore -d "$DATABASE_URL" --no-owner consorcio-16.dump`.
5. `ALTER EXTENSION postgis UPDATE;` y `ALTER EXTENSION pgrouting UPDATE;`
   hasta PostGIS 3.5 y pgRouting 4.0.
6. `alembic upgrade head` y comparar `count(*)` de las tablas de padrón,
   canales y catastro contra el conteo anotado antes del dump.

**pg_upgrade** (menos copia, más frágil; exige los dos clusters en el mismo
host):

1. Mismo backup `pg_dump -Fc` del paso anterior, por si el upgrade aborta.
2. Instalar binarios 17 al lado de los 16 (la imagen 17 trae solo la 17;
   hace falta un contenedor con ambos, o correr `pg_upgrade` desde un
   sidecar que monte el PGDATA viejo y uno nuevo).
3. `pg_upgrade --old-datadir /var/lib/postgresql/16/main --new-datadir /var/lib/postgresql/17/main --old-bindir /usr/lib/postgresql/16/bin --new-bindir /usr/lib/postgresql/17/bin --check`
   y, si el check pasa, el mismo comando sin `--check`.
4. Arrancar solo el cluster 17, `ALTER EXTENSION` como arriba, y apuntar
   `POSTGRES_HOST` / el digest del compose al tag `17-3.5-4.0` pineado.
5. Borrar el PGDATA 16 recién cuando un `SELECT count(*)` y un tile de
   Martin respondan.

La imagen de backup no sube a Alpine 3.23+: ahí desaparece
`postgresql16-client` y queda solo el cliente 17. Un `pg_dump` 17 de un
server 16 funciona, pero el restore de ese archivo custom contra un server
16 no. Mientras el server sea 16, el cliente del backup se queda en 16.

## Caddy (INF-01, INF-06)

Archivo stock, válido sin módulos extra: `deploy/Caddyfile`.
Con rate limit en la API (100/min por IP): `deploy/Caddyfile.with-ratelimit`.

1. En el server, guardar el Caddyfile actual: `cp /home/javier/caddy/Caddyfile /home/javier/caddy/Caddyfile.bak.$(date -u +%Y%m%d)`.
2. Copiar `deploy/Caddyfile` y ajustar los nombres. Los hosts vivos son
   `cc10demayo-api.javierzader.com` y `cc10demayo-tiles.javierzader.com`, no
   el placeholder `api.consorcio.{$DOMAIN}` si el dominio real es otro.
   Sustituir el placeholder o definir `DOMAIN` como lo hace el Caddy actual.
3. Definir `ACME_EMAIL`.
4. Validar **antes** de recargar:

   ```bash
   caddy validate --config /home/javier/caddy/Caddyfile
   caddy reload --config /home/javier/caddy/Caddyfile
   ```

5. Comprobar:

   ```bash
   curl -sI https://cc10demayo-api.javierzader.com/live | tr -d '\r' | grep -iE 'strict-transport|server:|via:|x-xss'
   ```

   Tiene que aparecer `strict-transport-security` con `preload`. No tienen que
   aparecer `server:` ni `via:` ni `x-xss-protection`. El bloque `header` del
   Caddyfile incluye `defer`: sin eso, `reverse_proxy` vuelve a escribir `Via`
   después de que `-Via` ya corrió (BE-05). Recargar el Caddyfile en el VPS
   es el paso que falta; el repo no puede hacerlo.

6. Rate limit, solo cuando haga falta y en otra ventana: `xcaddy build --with github.com/mholt/caddy-ratelimit`, instalar ese binario, validar `deploy/Caddyfile.with-ratelimit` y recién ahí recargar. Un Caddy stock rechaza la directiva `rate_limit` y se cae el proxy.

7. Preload de HSTS: el header ya viaja. **No** enviar el dominio a
   <https://hstspreload.org> hasta que cada subdominio del apex responda
   HTTPS. La sumisión es manual y tarda meses en revertirse. Un subdominio
   suelto no entra en la lista.

Los logs de acceso quedan en stdout en JSON (`docker logs` / journal del
servicio Caddy).

## Webhook de deploy (INF-09)

El receptor es `deploy/deploy_webhook.py`. Solo acepta POST `/hooks/deploy`
con Bearer, imágenes `ghcr.io/jnzader/consorcio-canalero/{backend,geo-worker}@sha256:…`
y un `revision` de 40 hex que no se haya aplicado ya. Compara el token con
`sha256` + `compare_digest`. Escucha en `127.0.0.1`.

En el server:

```bash
REPO=/home/javier/programacion/consorcio-canalero
sudo install -m 0755 "$REPO/deploy/deploy_webhook.py" /usr/local/bin/consorcio-deploy-webhook.py
sudo install -d -m 0750 -o javier -g javier /var/lib/consorcio-deploy /etc/consorcio
sudo tee /etc/consorcio/deploy-webhook.env >/dev/null <<'EOF'
DEPLOY_WEBHOOK_SECRET=<mismo valor que el environment secret de GitHub, 32+ caracteres>
STACK_DIR=/home/javier/stacks/consorcio
DEPLOY_WEBHOOK_STATE=/var/lib/consorcio-deploy/revisions
DEPLOY_DIGEST_ENV=/home/javier/stacks/consorcio/deploy-digests.env
EOF
sudo chmod 0600 /etc/consorcio/deploy-webhook.env
sudo cp "$REPO/deploy/deploy-webhook.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now deploy-webhook.service
curl -sS http://127.0.0.1:8090/health
```

Publicarlo solo a través de Caddy (sitio `deploy.…` del Caddyfile, o un
`handle /hooks/deploy` en el host de la API que haga `reverse_proxy` a
`127.0.0.1:8090`). `DEPLOY_WEBHOOK_URL` en GitHub tiene que ser esa URL
HTTPS. El puerto 8090 no se abre en el firewall.

`javier` está en el grupo `docker`. Eso equivale a root en el host: quien
puede hablarle al socket puede montar el disco del host. El unit lo deja
así porque `docker compose` lo necesita. No agregar a otros usuarios a ese
grupo.

El workflow escribe `BACKEND_DIGEST` / `GEO_WORKER_DIGEST` en
`deploy-digests.env` y corre `docker compose up -d`. El compose de
producción tiene que ser `docker-compose.prod.yml` (el que exige esos
digests). Si el server todavía usa el legado con `build:`, el webhook no
tiene efecto útil: terminar el corte de INF-07 antes de prender
`ENABLE_PRODUCTION_DEPLOY`.

## Environment `production` en GitHub (CI-06)

El job `deploy` de `deploy.yml` declara `environment: production`. Los
revisores obligatorios no se pueden poner en el YAML.

Antes del próximo deploy, en el repo de GitHub:

1. Settings → Environments → New environment → nombre exacto `production`.
2. Deployment protection rules → Required reviewers → la persona que aprueba un deploy a Hetzner.
3. Deployment branches: solo `main`.
4. Environment secrets → `DEPLOY_WEBHOOK_SECRET` (el mismo valor que en el server). Borrar el secret de repositorio con el mismo nombre para que un job sin este environment no lo vea.
5. Variables de repositorio que se quedan donde están: `ENABLE_PRODUCTION_DEPLOY` (kill switch) y `DEPLOY_WEBHOOK_URL`.

Si el environment no existe, GitHub lo crea vacío en el primer deploy y
**no** pide aprobación. Crearlo con revisores antes de poner
`ENABLE_PRODUCTION_DEPLOY=true`.

El kill switch sigue: con la variable distinta de `true` el job ni se
encola. Con la variable en `true`, el job espera la aprobación y recién
entonces hace el POST.

## Cloudflare Pages (CI-05)

Pages no tiene que publicar `main` solo. Publica la rama `pages-production`,
que este repo mueve solo cuando el workflow Frontend termina en verde en un
push a `main`.

Orden:

1. Mergear este cambio a `main` y esperar el workflow **Pages promote**. Crea o adelanta `pages-production` sin `--force`. Si la rama se desvió de `main`, el job falla a propósito: no reescribirla a mano con force; revisar por qué divergió.
2. Confirmar que la rama existe: `git ls-remote origin refs/heads/pages-production`.
3. En el dashboard de Cloudflare: Workers & Pages → `consorcio-canalero` → Settings → Builds & deployments.
4. Production branch: cambiar `main` por `pages-production`.
5. Guardar. El próximo deploy de producción sale de esa rama, no del push crudo a `main`.
6. Los preview de pull requests pueden seguir activos. No hacen falta para este hallazgo.

Hasta el paso 4, Cloudflare sigue publicando `main` aunque el workflow esté
verde. No hay forma de cambiar esa rama desde el repo.

Comprobar: un commit que rompa el job de tests de frontend no tiene que
mover `pages-production` (`gh api repos/JNZader/consorcio-canalero/commits/pages-production --jq .sha` queda en el SHA anterior).

## Backups, alerta y simulacro (INF-02, INF-13)

El crontab de `docs/RUNBOOK.md` §1.4.d queda reemplazado por timers. Si se
dejan los dos, el backup corre dos veces.

```bash
REPO=/home/javier/programacion/consorcio-canalero
sudo install -m 0755 "$REPO/deploy/backup.sh" /usr/local/bin/consorcio-backup.sh
sudo install -m 0755 "$REPO/deploy/backup-age-check.sh" /usr/local/bin/consorcio-backup-age-check.sh
sudo install -m 0755 "$REPO/deploy/restore-drill.sh" /usr/local/bin/consorcio-restore-drill.sh
sudo install -m 0755 "$REPO/deploy/notify-failure.sh" /usr/local/bin/consorcio-notify.sh
sudo cp "$REPO/deploy/backup.service" "$REPO/deploy/backup.timer" \
        "$REPO/deploy/backup-age-check.service" "$REPO/deploy/backup-age-check.timer" \
        "$REPO/deploy/notify@.service" /etc/systemd/system/
sudo install -d -m 0750 /etc/consorcio
# KEY=VALUE solamente. chmod 0600.
sudo tee /etc/consorcio/notify.env >/dev/null <<'EOF'
ALERT_WEBHOOK_URL=https://hooks.example/consorcio
# MAILTO=operador@example.com
EOF
sudo chmod 0600 /etc/consorcio/notify.env
sudo systemctl daemon-reload
sudo systemctl enable --now backup.timer backup-age-check.timer
sudo crontab -u javier -l   # borrar las dos líneas de backup-postgres / backup-volumes
```

El ETL semanal (`etl-refresh.service`) ahora tiene `OnFailure=notify@%n.service`.
Reinstalar el unit junto con el timer si en el server hay una copia vieja:

```bash
sudo cp "$REPO/deploy/etl-refresh.service" /etc/systemd/system/
sudo systemctl daemon-reload
```

El usuario `javier` del ETL y del backup está en el grupo `docker`. Eso es
root en la práctica. Está documentado a propósito; no es un usuario de
aplicación.

Primera corrida, para no esperar a las 03:20:

```bash
sudo systemctl start backup.service
cat /home/javier/stacks/consorcio/logs/backup-last-success
sudo systemctl start backup-age-check.service
```

La imagen de backup hay que reconstruirla una vez (subió de Alpine 3.20 a 3.22):

```bash
cd /home/javier/stacks/consorcio
docker compose --profile backup build --no-cache
```

### Simulacro de restore

Una vez por mes, contra una base que no es la viva. El script se niega a usar
`consorcio` o `consorcio_canalero`.

```bash
/usr/local/bin/consorcio-restore-drill.sh --check-target consorcio_restore_drill
```

`--execute` solo crea la base de simulacro si el compose del stack tiene un
servicio `postgres` (el archivo legado). En `docker-compose.prod.yml` Postgres
está afuera. Ahí el equivalente es:

```bash
docker exec -i shared-postgres psql -v ON_ERROR_STOP=1 -U postgres -d postgres \
  -c 'DROP DATABASE IF EXISTS consorcio_restore_drill;' \
  -c 'CREATE DATABASE consorcio_restore_drill;'
```

No uses el nombre de la base viva. El script se niega a `consorcio` y a
`consorcio_canalero`.

Seguir con el descifrado y el `psql` de RUNBOOK §3.6 apuntando a
`consorcio_restore_drill`. Anotar acá la duración y borrar la base.

**Último simulacro:** todavía no se ejecutó en el server con este procedimiento.

## Uptime (INF-04)

El contrato de los cuatro chequeos está en `deploy/uptime-monitors.json`
(API `/live`, API `/ready`, home, `/mapa`). Hay que crearlos a mano. El VPS
ya tiene Uptime Kuma (`DEPLOY.md`); UptimeRobot sirve si se prefiere un
monitor de fuera del mismo host. Un monitor que corre en el mismo CX33 no
avisa si se cae el VPS entero: al menos `/live` y la home tienen que estar
en un servicio externo.

En Uptime Kuma: Add Monitor → HTTP(s) → pegar cada URL del JSON → intervalo
5 min → notificación al mismo canal que `ALERT_WEBHOOK_URL`.

`/mapa` tiene que esperar HTTP 200. Si hoy responde 404, el monitor queda
rojo hasta el arreglo del fallback SPA. No cambiar el código esperado para
callarlo.

## Credencial de Earth Engine (GEE-01)

El proceso lee primero `GEE_KEY_FILE_PATH`. Si ese archivo existe, gana sobre
`GEE_SERVICE_ACCOUNT_KEY`. La identidad que guarda es mtime y tamaño del
archivo, o el sha256 del JSON de entorno: nunca la clave. Si el archivo
cambia, la siguiente llamada hace `ee.Reset()` y vuelve a inicializar, sin
reiniciar el proceso y sin rebuild de la imagen.

`docker-compose.prod.yml` monta `${GEE_CREDENTIALS_DIR:-./secrets/gee}` en
`/app/credentials` (solo lectura) en backend, celery-worker y geo-worker.
`secrets/` no se commitea. El directorio vacío es válido: si no hay archivo,
sigue valiendo el JSON de entorno.

Primera vez en el VPS (el repo no puede crear el directorio ni recrear los
contenedores):

```bash
cd /home/javier/stacks/consorcio
install -d -m 0755 secrets/gee
install -m 0644 /ruta/de/la/clave.json secrets/gee/gee-service-account.json
# 0644 para que el uid `app` de la imagen pueda leer el bind mount.
# El directorio del stack no tiene que ser público.
grep -q '^GEE_KEY_FILE_PATH=' .env || echo 'GEE_KEY_FILE_PATH=/app/credentials/gee-service-account.json' >> .env
docker compose up -d backend celery-worker geo-worker
```

Rotación, con el mount ya presente:

1. En GCP, crear la clave nueva de la service account. No borrar la vieja todavía.
2. `install -m 0644 clave-nueva.json secrets/gee/gee-service-account.json` (reemplazo atómico: escribir un temporal en el mismo directorio y `mv`).
3. La próxima llamada GEE del backend, del worker o del geo-worker relee el archivo. No hace falta `restart` ni una imagen nueva.
4. Confirmar en los logs que no aparece `No se pudo inicializar GEE`. Recién ahí revocar la clave vieja en GCP.
5. Si el server todavía usa solo `GEE_SERVICE_ACCOUNT_KEY` (sin archivo), el settings se carga al arrancar: rotar ese valor sí exige `docker compose up -d --force-recreate` de los tres servicios. Preferir el archivo.

## Métricas HTTP y GEE (OBS-02, GEE-02)

`GET /metrics` expone texto Prometheus 0.0.4, sin autenticación y fuera del
rate limit. Series:

- `http_responses_429_total{method,path}` — respuestas 429.
- `http_request_duration_seconds` — histograma por método y ruta (los UUID y los segmentos numéricos se colapsan a `{id}` y `{n}`).
- `http_requests_total{method,path,status}`.
- `gee_call_duration_seconds{operation}` — `getInfo` (cada lectura GEE) e `initialize`.

p95 de las llamadas GEE:

```promql
histogram_quantile(0.95, sum by (le, operation) (rate(gee_call_duration_seconds_bucket[5m])))
```

429 por ruta:

```promql
sum by (path) (rate(http_responses_429_total[5m]))
```

Los dos Caddyfile responden 404 a `/metrics` y a `/metrics/*` en los tres
hosts públicos (`@metrics`, antes del `reverse_proxy`). El proceso sigue sirviendo el
endpoint en la red de Docker: `http://consorcio-backend:8000/metrics`. El
puerto publicado del backend es `127.0.0.1:8000`, no la internet.

El scrape no está instalado en el VPS. Hay que agregarlo a mano contra esa
URL interna (Prometheus en la misma red, no contra el nombre público de la
API). Recargar el Caddyfile en el VPS sigue siendo el paso manual de la
sección Caddy: sin esa recarga el borde viejo todavía reenvía `/metrics`.

## Pisos de cobertura (CI-04)

Medidos en `main` el 2026-10-13. El piso sube hacia 80 % y se queda en el entero de esa medición cuando la cobertura real no llega.

- Backend: `--cov-fail-under=80` (antes 70). `tests/new/` con `.coveragerc` midió 80.82 %.
- Módulos críticos, en `gee-backend/scripts/critical_coverage_gate.py`: `app/auth/router.py` ≥ 27 % (medido 27.1 %), `app/core/rate_limit.py` ≥ 61 % (medido 61.5 %), `app/domains/denuncias/router.py` ≥ 80 % (medido 85.4 %).
- Frontend (`vitest.config.ts`): statements 78, branches 73, functions 76, lines 79 (medido 78.17 / 73.53 / 76.43 / 79.47).

## Parche de Mantine (CI-03)

`consorcio-web/patches/@mantine+core+9.7.2.patch` sigue al lock, que instala
9.7.2. El arreglo de `getEnv` y el de las transiciones en `env === "test"`
siguen haciendo falta en esa versión.
