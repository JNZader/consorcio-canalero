# Documentos — box sync and ops

Wave 1 of `openspec/changes/documentos/`: operator-only catalog + authenticated
download. Confidential file **bytes** never enter the public GitHub repo or
Cloudflare Pages. This runbook is how they reach the Hetzner box.

Product roadmap (not built here): Wave 2 RAG ignition → Wave 3 AI note editor.
See `openspec/changes/documentos/proposal.md`.

## What lives where

| Piece | Location |
|---|---|
| Catalog metadata (ids, titles, relative paths) | Public repo: `gee-backend/app/domains/documentos/catalog.py` |
| File bytes | Private clone `JNZader/tramites-consorcio` + box volume `consorcio-documentos` → `/app/documentos` |
| API | `GET /api/v2/documentos*` on backend (operator+) |
| UI | `/admin/documentos` on Cloudflare Pages (after FE merge to `main`) |

## Deploy order (skew)

1. Merge **backend** PR → `scripts/deploy-box.sh` on the box (no Alembic for this feature).
2. Apply compose sample mounts for `documentos-data` on the **live** box compose (hand-edited; git sample is `docker-compose.prod.yml`).
3. **Rsync** catalog-referenced files into the volume (below).
4. Merge **frontend** PR to `main` (Pages auto-deploys).
5. Owner deletes Cloudflare Pages project **`tramites-consorcio`** (agent reminds; does not delete).

## Permissions

Same precedent as GEE credentials (`docs/runbooks/infra-cicd-v6.md`):

```bash
# On the box, after the volume exists / after rsync into a staging dir:
install -d -m 0755 /path/to/documentos-tree
find /path/to/documentos-tree -type d -exec chmod 0755 {} +
find /path/to/documentos-tree -type f -exec chmod 0644 {} +
```

`uploads-init` in the prod compose sample `chown`s `/app/documentos` to `app:app`
and `chmod 0750` the root on each deploy.

## Rsync (laptop → box)

Source of truth for paths: relative paths in `catalog.py` (`docs/...`,
`visor_assets/...`). Sync **only** those trees (no `visor_assets/previews/`).

Example (adjust host alias and destination to the box layout):

```bash
# From the laptop, with the private clone checked out:
SRC="$HOME/programacion/tramites-consorcio"
HOST=consorcio-prod
# Staging dir on the box that will be copied into the volume, OR a bind path
# that already is the volume mount — pick one and stick to it.
DEST_STAGING="/var/lib/consorcio/documentos"

rsync -av --relative \
  "$SRC/./docs" \
  "$SRC/./visor_assets/codist" \
  "$SRC/./visor_assets/dnv" \
  "$SRC/./visor_assets/informes" \
  "$SRC/./visor_assets/t269-01" \
  "$SRC/./visor_assets/t269-03" \
  "$SRC/./mapas-cruce" \
  "${HOST}:${DEST_STAGING}/"
```

Then ensure the Docker volume content matches that tree under `/app/documentos`
(copy into the named volume, or bind-mount the staging dir — box-specific).

Verify from inside the backend container:

```bash
docker compose exec backend ls -la /app/documentos/visor_assets/codist
docker compose exec backend python -c \
  "from app.domains.documentos.catalog import DOCUMENTOS; print(len(DOCUMENTOS))"
```

Smoke as operador: `GET /api/v2/documentos` then download one known PDF.

## Backups

- `scripts/backup_volumes.sh` default `BACKUP_SOURCES` includes `/app/documentos`.
- Prod sample `backup-volumes` mounts `documentos-data:/app/documentos:ro`.
- On the box `.env`, if `BACKUP_SOURCES` is set explicitly, **append**
  `/app/documentos` (colon-separated). Missing it silently skips Documentos
  from restic.

## Regenerating the catalog metadata

When the private index gains/loses dossiers (laptop only):

```bash
node scripts/_extract_documentos_catalog.mjs \
  gee-backend/app/domains/documentos/catalog.py
```

Commit the regenerated `catalog.py` (metadata only). Re-rsync any new paths.

## Rollback

1. Revert FE → nav/route gone.
2. Revert BE → API gone.
3. Unmount volume on the box; leave or delete files deliberately.
4. Private `tramites-consorcio` remains the offline fallback until Pages is removed.

## Owner action (not automated)

Delete the Cloudflare Pages project for **`tramites-consorcio`** after Documentos
is live on consorcio admin and the box holds the files. Do not leave two homes
for the same confidential corpus.
