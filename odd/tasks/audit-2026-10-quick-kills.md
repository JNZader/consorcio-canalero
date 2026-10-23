# Work Unit: audit-2026-10-quick-kills

Batch of mechanical fixes from the 2026-10-23 exhaustive audit
(`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`):
fresh-clone bootstrap (C3/INF-1), production boot gate coverage (NUC-4),
and Makefile honesty (INF-3/INF-4). No application behavior changes beyond
failing earlier/louder where the audit found silent breakage.

## In

- docker-compose.yml: `REDIS_PASSWORD` falls back to `consorcio_dev_redis`
  instead of `:?`-failing the whole compose file; healthcheck uses the same
  fallback (plus `--no-auth-warning`). A fresh `git clone && docker compose up`
  boots again.
- .env.example: documents `REDIS_PASSWORD` and its relationship with
  `REDIS_URL`.
- setup.sh: creates a root `.env` with the dev `REDIS_PASSWORD` when absent
  (same value as the compose fallback so dev `REDIS_URL` without password
  keeps working; redis port is loopback-only).
- Makefile: `db-upgrade`/`db-downgrade` no longer swallow alembic failures
  behind `2>/dev/null || echo` (a broken migration now fails loudly instead
  of exiting 0).
- Makefile: removed `docker-monitoring`/`docker-scheduler` — both referenced
  compose profiles that do not exist anywhere and advertised a Flower URL
  that is not defined.
- app/config.py `_enforce_production_secrets`: production boots are refused
  when neither `HEALTHCHECK_HOST` nor a parseable `API_BASE_URL` is set —
  the exact condition under which the Docker healthcheck exits 1 forever and
  crash-loops a healthy app. Reuses the healthcheck's own URL parser.
- tests/new/test_config_production_gate.py: regression tests for the new
  gate rule (refuse / explicit host OK / parseable URL OK / dev never
  enforced).

## Out

- Prod/deploy compose files keep `:?` required secrets — that is correct
  there; only the dev file needed a default.
- `make redis-cli` NOAUTH fix (audit smell) — separate cleanup.
- Healthcheck env-file subtlety (`API_BASE_URL` set only via env_file is
  invisible to `os.environ` reads in healthcheck.py) — pre-existing, noted
  in the audit; not touched here.
- The `zz_users_fk_nullable`-style migration work and everything else in the
  audit's wave 3 — separate units.
