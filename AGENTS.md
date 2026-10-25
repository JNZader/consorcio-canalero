# Consorcio Canalero

Operational contract for this repository. `CLAUDE.md` is the local developer
setup. Where the two disagree about the Hetzner box, this file wins.

This is Consorcio Canalero 10 de Mayo. It is not biogas-platform. Both stacks
run on the same VPS. Consorcio commands stay in the consorcio checkout and
only name containers that start with `consorcio-`.

## Box deploy

The box is updated by `scripts/deploy-box.sh`, run on the box. The laptop does
not build or push these images.

The script builds `backend`, `worker`, `celery-beat`, and `geo-worker` locally.
It does not publish to GHCR, does not set `ENABLE_PRODUCTION_DEPLOY`, and does
not deploy the frontend. It saves the box `docker-compose.yml` and restores it
after `git reset --hard origin/main`. The compose on `origin/main` is the
development file.

It does not run Alembic. Schema changes are a separate, explicit step.

On 2026-10-24 the live database stamp was `0033_one_way_profile`. The image
running there reports that revision as `(head)` because the image predates
`conocimiento_008`. On current `main`, `conocimiento_008` revises
`0033_one_way_profile` and is the only Alembic head. `alembic upgrade head`
from a current checkout against that database would apply `conocimiento_008`.
Do not add that command to the deploy script.

`geo-worker` bind-mounts `gee-backend/app` and runs as uid 100. The checkout
inside the script uses `umask 022`. A tree left at mode `600` makes the worker
fail to import (`PermissionError` on `config.py` was the observed case). The
public tile proxy turns a worker status `>= 400` into `204`. MapLibre then
draws flat terrain. The health probe is `python -m app.healthcheck` inside
`consorcio-backend`. A curl to `127.0.0.1:8000/health` returns `400` because
the host header is rejected.

## Flags

`conocimiento_normas_enabled` defaults to false in `gee-backend/app/config.py`.
Leave it off. Do not ingest the production corpus as part of unrelated work.
