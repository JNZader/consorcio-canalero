# Proposal: Documentos (admin catalog + authenticated download)

## Intent

Operators of Consorcio Canalero 10 de Mayo keep ~25 live administrative dossiers
(notas to DNV / APRHI / Castelló, Co.Di.St. budgets, technical reports, CiDi
filings) and ~90 MB of attachments in a private static site
(`JNZader/tramites-consorcio`). That site is the wrong long-term home: no
consorcio auth, separate Cloudflare Pages project, and no path into the future
RAG + note-drafting workflow.

This change adds a **Documentos** section to the existing admin app so an
operator/admin can list those dossiers and download (or open PDF/JPG via blob
in a new tab) without putting confidential files in the public repo or on
Pages.

## Scope

### In scope (Wave 1 — this change)

| Area | Deliverable |
|---|---|
| Backend domain `documentos` | Code-defined catalog (JSON/Python); no DB, no Alembic |
| API | `GET /api/v2/documentos`, `GET /api/v2/documentos/{id}`, `GET /api/v2/documentos/{id}/archivo/{file_id}` — all `require_operator` |
| Binary serve | `StreamingResponse` + `Content-Disposition: attachment`; realpath jail under `documentos_root` |
| Frontend | `/admin/documentos` + nav item **Documentos** under Gestión; list/detail; `fetchAuthenticatedFile` + anchor / blob tab |
| SPA lockstep | `routeTree.gen.tsx` + `public/_worker.js` `SPA_ROUTES` + Cloudflare redirect tests |
| Auth gates | New paths in `tests/new/test_auth_gates.py` (401 unauthenticated; ciudadano → 403) |
| Ops | Documented box mount + rsync from private clone; `BACKUP_SOURCES` + prod backup mounts; startup `makedirs` for `documentos_root` |
| Catalog bridge | Opaque stable ids; metadata: group/tipo, expediente, destinatario, authors, dates, mime, relative path, `clasificacion` default `privado` or `institucional` |

### Out of scope / NON-goals (Wave 1)

- Upload, edit, delete, or version files from the UI.
- Database tables or migrations.
- Embedded PDF/HTML viewer (CSP `object-src 'none'`, `X-Frame-Options: DENY`).
- Inline open of `.html` / `.kmz` / `.docx` (download only).
- OCR / text extraction.
- Ingesting Documentos into the RAG corpus.
- AI note editor / generation UI.
- Renaming or extending the existing `tramites` domain, `/admin/tramites`, or
  Trámites API contracts (`TramiteCreate` / `TramiteResponse` untouched).
- Deleting the Cloudflare Pages project `tramites-consorcio` (owner action at
  the end — agent reminds, does not delete).
- Changing Caddy (full API host already proxied).

## Product roadmap (documented only — not built here)

| Wave | Name | Ships | Notes |
|---|---|---|---|
| **1** | Documentos bodega | This proposal | Binary serve ≠ corpus |
| **2** | RAG ignition | Owner ceremony (`docs/rag/runbook-encendido.md`); norms flag on | Documentos stay **out** of RAG until a later deliberate classify+ingest |
| **3** | AI note editor | In-app drafting with RAG + Documentos/expediente context | Sibling of Ley 8803 editor; that spec already defers “obra notes” |

Wave 1 leaves the **catalog identity contract** that Waves 2–3 will cite.
It does not implement retrieval or drafting.

## Decisions (confirmed 2026-11-24)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Dedicated** `documentos_root` default `/app/documentos` + dedicated Docker volume | Cleaner ACL/backup than nesting under denuncia uploads; same realpath jail pattern |
| D2 | Sync **catalog-referenced files only** (not entire `docs/` / previews tree) | Smaller attack + backup surface; catalog is source of truth |
| D3 | **Omit preview PNGs** from v1 attachments | Noise for operators; originals remain in private repo if needed later |
| D4 | Binary pattern = **`StreamingResponse`** (tramites/reuniones precedent), not `main.py` photo `Response` | Existing domain export style; ≤4.75 MB files fine |
| D5 | PR base = **`main`** (current practice); branch `feat/documentos*` | `CONTRIBUTING.md` develop path is stale vs 2026-11 merges |
| D6 | Chained PRs: **backend → frontend → ops/docs** | Avoid FE-on-Pages calling missing API; files rsynced before FE merge preferred |
| D7 | Wave-1 `clasificacion` = **`privado` for all** rows | Reclassify before any RAG use |
| D8 | List = summaries; **files only on detail** | Smaller list payload |

## Capabilities

### New

- `documentos-catalog-api` — authenticated list/detail of code catalog; opaque ids.
- `documentos-authenticated-download` — operator+ file download with path jail.
- `documentos-admin-ui` — admin route, nav, list/detail, download/open actions.
- `documentos-box-ops` — mount, rsync runbook, backup inclusion (docs + compose
  comments for the box-edited prod file).

### Modified

- Admin navigation / SPA route registry / auth-gates inventory.
- Backend settings: `documentos_root`.
- Dev/prod compose samples for the new volume (box still edited by hand).

## Approach

1. New screaming-architecture domain `gee-backend/app/domains/documentos/`
   without `models.py` (catalog module + schemas + service + router).
2. Catalog derived from the 25 `id`s in private `tramites-consorcio/index.html`
   groups (`notas`, `cidi`, `codist`, `conflictos`, informes/cruces) — content
   model only; do not port the static viewer UI.
3. Each file descriptor gets its own opaque `file_id`; relative path never
   appears in the URL.
4. Frontend mirrors Trámites download UX (`fetchAuthenticatedFile` + anchor);
   PDF/JPG optional “open in new tab” via `URL.createObjectURL` then
   `window.open` / revoke.
5. Ops PR documents: rsync command, permissions `0644`/`0755` (GEE credentials
   precedent), backup env, remind Pages teardown.

## Affected areas

| Area | Impact | Description |
|---|---|---|
| `gee-backend/app/domains/documentos/` | New | Domain (no models) |
| `gee-backend/app/api/v2/router.py` | Modified | `include_router` |
| `gee-backend/app/config.py` | Modified | `documentos_root` |
| `gee-backend/app/main.py` | Modified | startup `makedirs` |
| `gee-backend/tests/new/test_auth_gates.py` | Modified | 401/403 coverage |
| `gee-backend/tests/new/` (documentos) | New | catalog + jail + download tests |
| `consorcio-web/src/routeTree.gen.tsx` | Modified | `/admin/documentos` |
| `consorcio-web/public/_worker.js` | Modified | `SPA_ROUTES` |
| `consorcio-web/src/components/admin/AdminLayout.tsx` | Modified | nav item |
| `consorcio-web/src/components/admin/.../Documentos*` | New | panel/pages |
| `consorcio-web/tests/unit/cloudflareRedirects.test.ts` | Modified | lockstep |
| `consorcio-web/tests/unit/` (documentos) | New | download helper / panel tests as needed for coverage floors |
| `docker-compose.yml` / `docker-compose.prod.yml` | Modified | volume + mounts (prod = sample; live box edited) |
| `scripts/backup_volumes.sh` docs / env example | Modified | `BACKUP_SOURCES` includes documentos root |
| `docs/runbooks/` or `docs/` | New/Modified | rsync + mount runbook |
| `openspec/changes/documentos/` | New | this SDD |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Deploy skew: FE on Pages before API/files on box | High | PR order backend → sync files → frontend; document gate in ops PR |
| Path traversal via crafted id/path | Med | Opaque ids only; resolve under realpath prefix; tests for `..` |
| Accidental commit of confidential binaries | High | `.gitignore` patterns; CI/docs reminder; never copy into `consorcio-web/public` |
| Name collision with Trámites | Low if disciplined | Separate domain/routes/nav; leave Trámites contracts untouched |
| Catalog drift vs private repo | Med | Catalog in code; ops checklist when dossiers change; Wave 1 accepts deploy-to-update |
| Rate limit 100/60s on bulk download | Low | Document; human UI is fine |
| Box compose ≠ git | High | Ops PR is documentation + sample compose; operator applies on box |
| Ciudadano probing endpoints | Med | Auth gates + explicit 403 tests |

## Rollback plan

1. Revert the frontend PR → nav/route gone; Pages no longer calls Documentos.
2. Revert the backend PR → endpoints gone; remove router include.
3. On the box: unmount/remove `documentos` volume mount; leave files on disk or
   delete deliberately.
4. No DB migration to reverse.
5. Private `tramites-consorcio` remains the offline fallback until Pages is
   deleted by the owner.

## Dependencies

- Private clone of `JNZader/tramites-consorcio` for catalog authoring + rsync source.
- Operator/admin accounts on the consorcio API.
- Box SSH (`consorcio-prod`) for volume + rsync (ops PR / ceremony, not laptop `deploy-box` for files).
- Existing `fetchAuthenticatedFile` / Bearer auth (no new credential mechanism).

## Delivery strategy

Interactive SDD. At **Tasks**, confirm chained PRs (expected >400 LOC):

1. **PR-A backend** — domain, config, auth gates, unit tests.
2. **PR-B frontend** — route, nav, UI, SPA lockstep, Vitest coverage.
3. **PR-C ops/docs** — compose samples, backup, rsync runbook, Pages deletion reminder.

Files never travel in git. Rsync is a box/operator step referenced by PR-C.

## Success criteria

- [ ] Operator can open `/admin/documentos`, see all 25 catalog dossiers grouped, open detail.
- [ ] Authenticated download of a known PDF succeeds; unauthenticated → 401; ciudadano → 403.
- [ ] Path jail rejects `..` / absolute escapes (unit tests green).
- [ ] Filenames never appear in URL path; only opaque ids.
- [ ] PDF open uses blob new tab; no iframe/object.
- [ ] SPA_ROUTES ↔ routeTree lockstep test green; Vitest floors held (78/73/76/79).
- [ ] No confidential file in the public tree (`git status` / intentional ignore).
- [ ] Runbook lists rsync, permissions, backup env, and “delete Pages tramites-consorcio”.
- [ ] Trámites API contract tests still pass unchanged.

## Open questions

1. Confirm D1–D6 above (defaults baked into Design if approved).
2. Exact `clasificacion` default per group (`privado` for all vs `institucional`
   for outbound notes already filed with agencies)? Propose: **all `privado` in
   Wave 1**; Wave 2/3 reclassify before any RAG use.
3. Should list endpoint return file descriptors inline or only on detail?
   Propose: **summary on list, files on detail** (smaller payload).
