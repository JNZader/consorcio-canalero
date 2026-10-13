# Application PostgreSQL role (DB-04)

The official Postgres image makes `POSTGRES_USER` a superuser. The API must
not use that identity at runtime: `COPY … PROGRAM` as superuser is RCE inside
the database container.

| Component | Role | Scope |
|---|---|---|
| `migrate` / Alembic | `consorcio` (bootstrap superuser) | DDL |
| Backend, workers, beat | `consorcio_app` | DML, `statement_timeout=15s`, `idle_in_transaction_session_timeout=60s`, no `SUPERUSER` |

This script does **not** `REASSIGN OWNED`. Table ownership stays on the migrator.
The materialized views the app refreshes (`mv_dashboard_geo_stats`,
`mv_hci_por_zona`, `mv_alertas_resumen`, `mv_suelos_por_zona`,
`mv_canales_por_zona`, `mv_caminos_por_zona`, `vt_parcelas_catastro`) and
their indexes are transferred to `consorcio_app`. PostgreSQL has no
`GRANT REFRESH`, and `REFRESH CONCURRENTLY` cannot run inside a function, so
ownership is the privilege that lets the non-superuser role refresh them.

`CREATE EXTENSION` stays on the migrator. Request handlers only read
`pg_extension`; they do not install it.

The script does **not** set a password. After `CREATE ROLE`, login is unusable until
`\password consorcio_app` in an interactive `psql`.

The role is created here, after migrations. Re-run this script after
`alembic upgrade head` so a view added by a later migration is owned by the
app role. The migration `zz_audit_v6_db` does the same transfer when the role
already exists.

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
