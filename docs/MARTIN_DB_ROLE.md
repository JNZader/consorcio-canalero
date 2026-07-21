# Rol PostgreSQL de solo lectura para Martin

Martin es un servicio público de teselas. Debe conectarse con una identidad distinta
del backend y con permisos que no permitan consultar tablas operativas ni ejecutar
mutaciones.

## Contrato de acceso

| Componente | Rol | Alcance |
|---|---|---|
| Backend y migraciones | `consorcio` | Propietario de la aplicación |
| Martin | `consorcio_martin` | `CONNECT`, `USAGE` y `SELECT` sobre tres vistas |

El rol `consorcio_martin` recibe `SELECT` exclusivamente sobre:

- `public.vt_zonas_operativas`
- `public.vt_puntos_conflicto`
- `public.vt_canal_network`

No recibe escritura sobre esas vistas, acceso a otras relaciones, secuencias,
funciones de aplicación, creación de objetos, tablas temporales ni membresías de
otros roles. Las funciones pertenecientes a extensiones como PostGIS y pgRouting
conservan sus ACL de extensión.

`default_transaction_read_only=on` es defensa adicional; la barrera efectiva son
los `GRANT` y `REVOKE` verificados por
`scripts/provision_martin_reader.sql`.

## Antes de aplicar

1. Hacé un backup y confirmá que las migraciones vigentes están aplicadas y crean las tres vistas permitidas.
2. Auditá otros roles que usen privilegios heredados de `PUBLIC`. El script cierra
   `CONNECT`, `TEMPORARY`, relaciones y secuencias públicas en esta base. Otorgá
   permisos explícitos a cualquier integración legítima antes de ejecutarlo.
3. Definí en el archivo `.env` una credencial independiente para Martin. No la
   reutilices para `DATABASE_URL` y no la pases en argumentos del shell.

El script no contiene ni cambia la credencial del rol. Si crea el rol por primera
vez, el login queda inutilizable hasta completar el paso interactivo.

## Stack principal: PostgreSQL compartido

Primero actualizá esquema e imágenes sin iniciar Martin:

~~~bash
cd /home/javier/stacks/consorcio
docker compose pull backend
docker compose run --rm migrate
~~~

Desde el checkout del repositorio, aplicá la política de permisos:

~~~bash
cd /home/javier/programacion/consorcio-canalero
docker exec -i shared-postgres   psql -X -U postgres -d consorcio_canalero   --set=database_name=consorcio_canalero   --set=app_role=consorcio   --set=martin_role=consorcio_martin   --file=- < scripts/provision_martin_reader.sql
~~~

Establecé o rotá la credencial sin exponerla en el historial ni en la lista de
procesos:

~~~bash
docker exec -it shared-postgres   psql -X -U postgres -d consorcio_canalero
~~~

Dentro de `psql`:

~~~text
\password consorcio_martin
\q
~~~

Guardá el mismo valor únicamente en
`/home/javier/stacks/consorcio/.env`:

~~~env
MARTIN_DB_URL=postgresql://consorcio_martin:VALOR_SECRETO@shared-postgres:5432/consorcio_canalero
~~~

Después iniciá o recreá los servicios:

~~~bash
cd /home/javier/stacks/consorcio
docker compose up -d
docker compose ps
~~~

## Stack legado embebido

El stack `docker-compose.deploy.yml` usa la base configurada como `POSTGRES_DB`
en `consorcio-postgres`. El superusuario de bootstrap es el valor efectivo de
`POSTGRES_USER`, que Compose deriva de `DB_USER` (con `consorcio` como default).
No asumas que existe un rol llamado `postgres`.

Los comandos siguientes hacen que Compose cargue explícitamente `.env`. Las
referencias a `POSTGRES_USER` y `POSTGRES_DB` se expanden dentro del contenedor,
con comillas, y ninguna credencial se pasa en argumentos:

~~~bash
cd /home/javier/programacion/consorcio-canalero
docker compose --env-file .env -f docker-compose.deploy.yml run --rm migrate

docker compose --env-file .env -f docker-compose.deploy.yml exec -T postgres \
  sh -ceu '
    exec psql -X \
      --username "$POSTGRES_USER" \
      --dbname "$POSTGRES_DB" \
      --set=database_name="$POSTGRES_DB" \
      --set=app_role="$POSTGRES_USER" \
      --set=martin_role=consorcio_martin \
      --file=-
  ' < scripts/provision_martin_reader.sql
~~~

Establecé o rotá la credencial en una sesión interactiva del mismo contenedor:

~~~bash
docker compose --env-file .env -f docker-compose.deploy.yml exec postgres \
  sh -ceu 'exec psql -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"'
~~~

Dentro de `psql`, ejecutá `\password consorcio_martin` y luego `\q`. Copiá
el valor únicamente a `MARTIN_DB_URL` en `.env` y recién entonces levantá Martin.

## Verificación y reejecución

La salida del script incluye:

- atributos del rol: solo `rolcanlogin` debe ser verdadero;
- base/esquema: `db_connect` y `schema_usage` verdaderos; creación y temporales
  falsos;
- tres vistas: `can_select=true` y todas las columnas de escritura falsas;
- cuatro contadores `unexpected_*`: todos deben ser `0`.

Confirmá además que Martin anuncia únicamente las tres fuentes:

~~~bash
curl --fail --silent http://localhost:3000/health
curl --fail --silent http://localhost:3000/catalog
~~~

Podés volver a ejecutar el script después de cada migración. Es idempotente y
repara ACL o membresías que se hayan desviado, pero aborta si falta una vista, el
rol de aplicación no existe, la conexión apunta a otra base o el lector es dueño
de objetos. En ese último caso, reasigná la propiedad de forma explícita antes de
reintentar; un propietario conserva permisos implícitos aunque se revoquen ACL.
