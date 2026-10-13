# audit-v6-wave-o

Wave O: DB-04. Stacked on `feat/audit-v6-wave-n` (#495).

## In

- [x] `provision_app_rw.sql`: LOGIN, no superuser, 15s timeout, DML grants.
- [x] Compose runtime can take `APP_DATABASE_URL`; migrate stays on migrator.
- [x] Docs. No live Postgres.

## Out

REASSIGN OWNED, Hetzner apply, CODE-02, UX-25, UI-04/05.
