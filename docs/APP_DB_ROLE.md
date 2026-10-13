# Application PostgreSQL role (DB-04)

The official Postgres image makes `POSTGRES_USER` a superuser. The API must
not use that identity at runtime: `COPY … PROGRAM` as superuser is RCE inside
the database container.

| Component | Role | Scope |
|---|---|---|
| `migrate` / Alembic | `consorcio` (bootstrap superuser) | DDL |
| Backend, workers, beat | `consorcio_app` | DML, `statement_timeout=15s`, no `SUPERUSER` |

This script does **not** `REASSIGN OWNED`. Ownership stays on the migrator.
It does **not** set a password. After `CREATE ROLE`, login is unusable until
`\password consorcio_app` in an interactive `psql`.

## Before applying

1. Backup. Confirm restore.
2. Run migrations as the migrator.
3. Put `APP_DATABASE_URL` in `.env` (different password from `DATABASE_URL`).
4. Do not pass the password on the shell.

~~~bash
cd /home/javier/programacion/consorcio-canalero
docker exec -i shared-postgres psql -X -U postgres -d consorcio_canalero \
  --set=database_name=consorcio_canalero \
  --set=migrator_role=consorcio \
  --set=app_role=consorcio_app \
  --file=- < scripts/provision_app_rw.sql
~~~

Then `\password consorcio_app` and point backend `DATABASE_URL` at
`APP_DATABASE_URL`. Leave `migrate` on the migrator URL.

Do not run this against Hetzner from an agent session without an explicit backup.
