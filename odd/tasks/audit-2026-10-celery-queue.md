# audit-2026-10-celery-queue

Celery queue routing fix on `feature/audit-c2-celery-queue` (from develop `16eb44ef`). The 2026-10-23 audit found `task_routes` matched only `geo.*` (Celery applies these patterns with re.match), so the three user-facing gee.* long tasks (`gee.analyze_flood`, `gee.supervised_classification`, `gee.sar_temporal`) fell to the default `celery` queue and were consumed by the maintenance worker (no GDAL, 512MB, concurrency=2) instead of the geo worker.

## In

- [x] `gee-backend/app/core/celery_app.py`: `task_routes` enumerates the three gee.* task names explicitly. No `gee.*` pattern — geo-worker routing is a per-task opt-in (mirroring `RECOVERABLE_LONG_TASKS`), so a future gee.* task cannot silently land on the single-concurrency GDAL worker. Comment documents the audit finding.
- [x] `gee-backend/tests/new/test_celery_recovery.py`: `test_recoverable_long_tasks_route_to_the_geo_queue` resolves every `RECOVERABLE_LONG_TASKS` name plus `geo.warm_gee_layers` through Celery's own router (`celery_app.amqp.router.route({}, name)`) and asserts queue == `geo`. Verified red on the unfixed table (`gee.analyze_flood` -> `celery`) by stashing the fix.
- [x] 17 passed in `tests/new/test_celery_recovery.py` + `tests/new/test_celery_beat.py` (TEST_DATABASE_URL against localhost:15432, `test_audit_c2` DB); ruff clean on both changed files.

## Out

Draining messages already queued on the default `celery` queue: any gee.* messages published before this fix are still addressed to `celery`, so the maintenance worker will pick them up and fail them (no GDAL). Options: purge + republish via the outbox (intents are retained), or point a temporary geo-capable worker at `-Q celery`. Operational step, not a code change — not implemented here.
