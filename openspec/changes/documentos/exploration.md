# Exploration: Documentos (admin catalog + authenticated download)

**Change:** `documentos`
**Base:** `origin/main` @ `c012e893` (worktree `feat/documentos`)
**Mode:** interactive SDD — this file is Explore only; no implementation.
**Date:** 2026-11-24

## Intent (product)

Add an admin section **Documentos** (`/admin/documentos`) so operators can browse
~25 administrative dossiers of Consorcio Canalero 10 de Mayo and download their
attachments. Files are confidential: they must never enter the public GitHub
repo nor Cloudflare Pages.

### Product roadmap (out of this change's build scope — document only)

Agreed arc; **Wave 1 keeps the current v1 scope**. Later waves are recorded so
the catalog contract does not paint the product into a corner.

| Wave | Name | What ships | Depends on |
|---|---|---|---|
| **1 (this change)** | Documentos bodega | Code catalog + operator download + box file mount + backups documented | — |
| **2** | RAG ignition | Owner ceremony in `docs/rag/runbook-encendido.md`; flip `conocimiento_normas_enabled` | Wave 1 not required for norms corpus; Documentos stay **out** of RAG until deliberately classified + ingested |
| **3** | AI note editor | In-app drafting aid using RAG + Documentos/expediente context | Waves 1+2; privacy fail-closed |

Wave 3 is **not** a reuse of the Ley 8803 access-request editor
(`gee-backend/app/domains/conocimiento/editor.py` + `openspec/specs/access-request-editor/`).
That editor already exists, is slot-based and fail-closed, and its spec
explicitly defers **obra notes** as a later feature. Wave 3 is that later
feature (or a sibling), not a fork of 8803 templates.

**Bridge that Wave 1 must leave behind (metadata only, no RAG/OCR/editor code):**

- Stable opaque document / file ids (not filenames in URLs or logs).
- Catalog fields rich enough to become RAG provenance later: `tipo` / `group`,
  `destinatario`, `expediente`, authors, dates, mime, relative path,
  `clasificacion` defaulting to `privado` or `institucional`.
- Hard boundary: **serving a binary ≠ making it a recoverable corpus unit**.

## Validated facts (against `main`)

### Auth and download pattern

| Claim | Evidence | Verdict |
|---|---|---|
| Bearer-only API auth | `gee-backend/app/auth/dependencies.py` (`BearerTransport`) | OK |
| `require_operator` = operador\|admin | `dependencies.py:391`; tramites uses `require_admin_or_operator` via lazy `_require_operator()` | OK — reuse tramites pattern |
| `fetchAuthenticatedFile` exists | `consorcio-web/src/lib/api/core.ts:454` | OK |
| `LONG_TIMEOUT` = 60s | `core.ts:18` | OK |
| No `access_token` in query URLs | `core.ts:428` rejects; pinned by `tests/unit/apiCoreHelpers.test.ts` | OK |
| No cookie/auth_request for arbitrary binaries | Protected photos hard-wired to `/uploads/denuncias/` | OK — Documentos must use fetch+blob+anchor |

### Why not embed / open inline

| Claim | Evidence | Verdict |
|---|---|---|
| `object-src 'none'` | `consorcio-web/public/_headers` CSP | OK |
| `X-Frame-Options: DENY` | Caddy, backend middleware, Pages `_headers`, nginx Dockerfile | OK |
| Open PDF in new tab via `blob:` URL | Required; iframe/object blocked | OK |

`.html` / `.kmz` / `.docx` → download only (no inline open). PDF/JPG may open
via blob in a new tab; still no embed.

### Domain and naming collision

| Claim | Evidence | Verdict |
|---|---|---|
| Domain `tramites` already exists | `gee-backend/app/domains/tramites/` (~150 LOC each file); router prefix `/tramites` | OK |
| Admin nav + route `/admin/tramites` | `AdminLayout.tsx` Gestión; `routeTree.gen.tsx` `adminTramitesRoute` | OK |
| Name **Documentos** is mandatory | Collision would break contracts in `test_admin_frontend_contracts.py` + `admin-api-contracts.json` | OK — never reuse Trámites |

### Binary response pattern

| Claim | Evidence | Verdict |
|---|---|---|
| `FileResponse` unused | True for current code | OK |
| Prefer existing export pattern | `tramites/router.py`, `reuniones`, `finanzas`, geo use **`StreamingResponse`** with `Content-Disposition: attachment` | **Prefer StreamingResponse** over `main.py` in-memory photo `Response` |

### Storage / ops

| Claim | Evidence | Verdict |
|---|---|---|
| `uploads_root` default `/app/uploads` | `config.py:569`; `makedirs` at `main.py:328` | OK |
| Volume `consorcio-denuncia-uploads` | compose + prod compose | OK |
| New root needed | Recommend `documentos_root` (config) default under uploads or sibling `/app/documentos`; create at startup | Open decision for Design |
| Path traversal precedent | Denuncia photos: `realpath` + prefix check under `…/denuncias` (`main.py:396-397`) | **Must clone for Documentos** |
| Caddy | Full API host proxied; no change for `/api/v2/documentos/*` | OK |
| `deploy-box.sh` never runs Alembic | `scripts/tests/test_deploy_box_script.py` | OK — no migrations in v1 |
| `BACKUP_SOURCES` | `scripts/backup_volumes.sh` default `/app/uploads:/data/geo` | New root must be added to env **and** backup-volumes mounts in prod compose (box-edited) |

### Frontend routing lockstep

| Claim | Evidence | Verdict |
|---|---|---|
| `routeTree.gen.tsx` hand-maintained | File header comment confirms no codegen plugin | OK |
| `SPA_ROUTES` must match | `public/_worker.js` + `tests/unit/cloudflareRedirects.test.ts` | Adding `/admin/documentos` requires **routeTree + SPA_ROUTES + test expectations** |
| Vitest floors | `vitest.config.ts`: statements 78 / branches 73 / functions 76 / lines 79 | Do not regress |

### Auth gates CI

New sensitive endpoints must appear in `gee-backend/tests/new/test_auth_gates.py`
(401 without auth) in the **same** PR as the router.

### Branch / PR base

| Claim | Evidence | Verdict |
|---|---|---|
| `CONTRIBUTING.md` says `feature/* → develop → main` | File present | Stale vs practice |
| Recent merges (e.g. #776) | `baseRefName: main`, branch `feat/…` | **Propose PRs against `main`** with `feat/documentos` (and chained branches) |

### Worktree isolation

| Claim | Evidence | Verdict |
|---|---|---|
| Other engineer on `feat/informe-area-pr1` | Not present in this machine's worktree list | Still work only in `worktrees/consorcio-documentos` |

## Source corpus (`tramites-consorcio`)

Private clone: `/home/javier/programacion/tramites-consorcio` (branch `master`).
Content reference: `index.html` (static viewer) — **content model only**, not UI to copy.

### Catalog shape in `index.html`

**25 unique dossier `id`s** (matches the brief):

| group | count | example ids |
|---|---|---|
| `notas` | 7 | `nota-01` … `nota-04`, reiteraciones |
| `cidi` | 6 | `cidi-1` … `cidi-6` |
| `codist` | 5 | `codist-p-sar`, `p-ach`, `p-sms`, `p-mln`, `p-des` |
| `conflictos` | 3 | `t269-01-alcantarilla`, `t269-03-*` |
| `informes-tecnicos` / `informes` / `cruces` | 2+1+1 | `informe-stehli-r01`, `plano-t391-5`, `diag-1` |

Each entry already carries `expediente`, badges, attachment URLs (pdf/tex/kmz/jpg/html),
and rich HTML previews. **v1 should derive the code catalog from this inventory**,
not invent a parallel taxonomy.

### Co.Di.St. presupuestos (verified in index)

| id | file | badge / monto |
|---|---|---|
| `codist-p-sar` | `visor_assets/codist/p-sar.pdf` | $3.350.000 (ya pago CGIC) |
| `codist-p-ach` | `p-ach.pdf` | $8.165.000 |
| `codist-p-sms` | `p-sms.pdf` | (index; re-check exact badge in propose) |
| `codist-p-mln` | `p-mln.pdf` | |
| `codist-p-des` | `p-des.pdf` | |

Authors (informe R01): Ing. Pablo T. Stehli + Ing. Mauricio A. Di Febo (Co.Di.St., Villa María).

### Files on disk (measured)

| Path | Files | Size |
|---|---|---|
| `visor_assets/` + `mapas-cruce/` | 94 | ~74 MB |
| Whole clone excl. `.git`/`.wrangler` | ~157 | ~88 MB |
| Heaviest file observed | `t269-01/fig-04-detalle-falla.jpg` | ~4.75 MB |

Extensions under assets: `.png` 43, `.pdf` 29, `.jpg` 22 (+ others in `docs/`).
There is also a large `docs/` tree (notes TEX/PDF/HTML) referenced by some
`url` fields — catalog build must decide which trees sync to the box
(`visor_assets` + `mapas-cruce` + selected `docs/` vs full tree).

**Correction vs brief:** ~90 MB / ~160 files is the right order of magnitude for
the clone; pure `visor_assets`+`mapas` alone is ~94 files / ~74 MB.

## Existing conocimiento surface (Wave 2–3 context)

- Domain `gee-backend/app/domains/conocimiento/` is complete for norms RAG;
  flag `conocimiento_normas_enabled` defaults **off**.
- Privacy: units carry `clasificacion` `publico` \| `institucional` \| `privado`;
  egress allowlist `CLASIFICACIONES_ENVIABLES` = publico+institucional.
- Admin already has **Consultas normativas** (`/admin/conocimiento`, admin-only).
- Documentos (operator+) is a **different** nav item under Gestión — next to
  Trámites, not inside Conocimiento.

## Proposed API sketch (for Propose — not binding)

```
GET  /api/v2/documentos              → list catalog (operator+)
GET  /api/v2/documentos/{id}         → dossier detail + file descriptors
GET  /api/v2/documentos/{id}/archivo/{file_id}
                                     → StreamingResponse attachment (operator+)
```

Ids opaque; relative paths resolved under `documentos_root` with realpath jail.
No upload, no delete, no DB.

## Frontend sketch (for Propose — not binding)

- Route `/admin/documentos` + nav item **Documentos** in Gestión (operator+).
- List/filter by group; detail shows metadata + download / open-PDF actions.
- Downloads via `fetchAuthenticatedFile` + anchor; PDF open = `URL.createObjectURL` + `window.open`.
- Sync `SPA_ROUTES` / Cloudflare worker.

## Delivery constraints

1. **No Alembic / no DB** in Wave 1.
2. **Files never in public git or Pages** — rsync/box mount only.
3. **PR order:** backend (+ auth gates) → frontend (+ SPA lockstep) → ops/docs
   (compose mounts, `BACKUP_SOURCES`, rsync runbook, remind delete Pages project
   `tramites-consorcio`).
4. Deploy skew: merge/deploy backend + sync files **before** frontend hits `main`.
5. `strict_tdd: true` in `openspec/config.yaml`.
6. Reminder at end: user deletes Cloudflare Pages project for `tramites-consorcio`.

## Risks / open questions for Propose

1. **`documentos_root` location:** nested under `/app/uploads/documentos` (inherits
   denuncia volume) vs dedicated volume `/app/documentos`. Nested is simpler ops;
   dedicated is cleaner backup/ACL. Prefer dedicated volume unless box friction wins.
2. **Which trees sync:** only paths referenced by the 25-id catalog vs whole
   `docs/` + previews. Prefer **catalog-referenced files only** to shrink attack
   and backup surface.
3. **Previews (PNG):** include as downloadable attachments or omit in v1?
   Recommend omit unless operator needs them — cuts noise.
4. **Ciudadano role:** must get 403 on all Documentos endpoints (operator+ only).
5. **Rate limit:** 100 req/60s authenticated — fine for human browsing; document
   that bulk download scripts can trip it.
6. **OpenSpec README** in repo is stale (does not list all live changes) — out of
   scope; do not “fix” it in this change unless asked.

## Success criteria for Explore

- [x] Auth/download/CSP/tramites-collision/storage/CI hooks verified on `main`
- [x] Corpus inventory measured (25 ids, groups, sizes, Co.Di.St. montos)
- [x] Roadmap Waves 1–3 written without expanding Wave 1 build scope
- [x] Open questions listed for Propose

## Next phase

**Propose** → `proposal.md`: intent, in/out of scope (Wave 1 only), roadmap
appendix, affected areas, risks, rollback, success criteria, chained-PR plan.
