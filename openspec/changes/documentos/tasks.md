# Tasks: Documentos (Wave 1)

Strict TDD: ON (`openspec/config.yaml` `strict_tdd: true`).
Worktree: `/home/javier/programacion/worktrees/consorcio-documentos` · branch `feat/documentos`.
Never touch another engineer's tree. Never commit confidential file bytes.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900–1400 (catalog metadata dominates; tests significant) |
| 400-line budget risk | High (will exceed) |
| Chained PRs recommended | Yes |
| Suggested split | PR-A backend → PR-B frontend → PR-C ops/docs |
| Delivery strategy | ask-on-risk (locked D6) |
| PR base | `main` |

| Unit | Goal | PR | Focused tests | Rollback |
|------|------|----|---------------|----------|
| A | Domain + auth + jail + compose dev volume | PR-A | `pytest tests/new/test_documentos_*.py tests/new/test_auth_gates.py` | Revert domain + router/config/main/compose hunks |
| B | Admin UI + SPA lockstep | PR-B | vitest cloudflare + documentos/mime tests; `tsc` | Revert FE routes/nav/panel |
| C | Prod sample + runbook + backup docs | PR-C | contract greps / doc review | Revert docs/compose.prod sample |

---

## PR-A — Backend

### Phase A0: Skeleton + schemas (TDD)

- [x] A0.1 RED: `tests/new/test_documentos_schemas.py` — `DocumentoResumen` / `DocumentoDetalle` / `ArchivoPublico` reject `relative_path` field; require `clasificacion=="privado"` on fixtures.
- [x] A0.2 GREEN: create `gee-backend/app/domains/documentos/schemas.py` (+ `__init__.py`).

### Phase A1: Catalog module (TDD)

- [x] A1.1 RED: `tests/new/test_documentos_catalog.py` — exactly 25 dossier ids; groups match exploration counts (notas 7, cidi 6, codist 5, conflictos 3, remaining informes/cruces); every row `clasificacion=="privado"`; every `ArchivoCatalogo.relative_path` is relative (no leading `/`); no preview `.png` under `visor_assets/previews/` referenced; file ids match `{dossier_id}__{slug}` and are unique.
- [x] A1.2 GREEN: author `catalog.py` from private `tramites-consorcio/index.html` (metadata + paths only). Prefer paths under `visor_assets/` and catalog-referenced `docs/` files; omit previews.
- [x] A1.3 RED: `list_resumenes(group=None|str)` / `get_detalle(id)` / `get_archivo(dossier_id, file_id)` pure accessors.
- [x] A1.4 GREEN: implement accessors on the catalog.

### Phase A2: Path jail + service (TDD)

- [x] A2.1 RED: `tests/new/test_documentos_jail.py` — with `tmp_path` as `documentos_root`, accept in-root file; reject `../`, absolute escapes, symlink escape if feasible; missing file → not found.
- [x] A2.2 GREEN: `service.py` `resolve_archivo_path` + stream opener using realpath jail (design algorithm).
- [x] A2.3 RED: service list/detail map catalog → schemas without leaking `relative_path` in `.model_dump()`.
- [x] A2.4 GREEN: mapping helpers in service.

### Phase A3: Router + config + wiring (TDD)

- [x] A3.1 RED: `tests/new/test_documentos_router.py` — TestClient: operator list 200 `{items}` len 25; filter `group=codist` → 5; detail 200 with `files`; unknown id 404; download 200 + `attachment` + correct content-type for a tiny fixture file seeded under tmp root (monkeypatch `documentos_root` + mini catalog or path override).
- [x] A3.2 GREEN: `router.py`; `config.documentos_root`; `main.py` makedirs; `api/v2/router.py` include.
- [x] A3.3 RED: extend `tests/new/test_auth_gates.py` — unauthenticated GET list/detail/download → 401.
- [x] A3.4 GREEN: ensure Depends(operator) on all three routes (ciudadano → 403 covered in router tests if role fixture exists; else add).
- [x] A3.5 GREEN: `docker-compose.yml` — volume `consorcio-documentos` mounted at `/app/documentos` on backend (and API-serving services that share uploads pattern).

### Phase A4: Backend verification gate

- [x] A4.1 Run Verification · Backend commands below; record observed results in Apply notes.
- [x] A4.2 Confirm `test_admin_frontend_contracts.py` still green (Trámites untouched).
- [x] A4.3 Confirm infra contracts still green (`test_deploy_box_script.py`, `test_ci_workflow_contracts.py` / `test_infra_v6_contracts.py` as applicable — no forbidden curl/wget; Dockerfile `mkdir` string intact).

---

## PR-B — Frontend

### Phase B0: Pure mime helper (TDD)

- [x] B0.1 RED: `consorcio-web/tests/unit/documentosMimeActions.test.ts` — PDF/JPEG → open+download; HTML/KMZ/DOCX/TEX → download only.
- [x] B0.2 GREEN: `src/lib/documentos/mimeActions.ts` (`canOpenInTab`).

### Phase B1: Route + SPA lockstep (TDD)

- [x] B1.1 RED: expect `cloudflareRedirects` / SPA lockstep to fail until route+worker updated (or add assertion for `/admin/documentos` first).
- [x] B1.2 GREEN: `routeTree.gen.tsx` admin Documentos route (auth gate like Trámites); `public/_worker.js` `SPA_ROUTES`; nav item **Documentos** in `AdminLayout` Gestión.

### Phase B2: Panel UI (TDD)

- [x] B2.1 RED: unit test — download action calls `fetchAuthenticatedFile` with `/documentos/{id}/archivo/{fileId}` and uses `LONG_TIMEOUT` (mock).
- [x] B2.2 GREEN: `DocumentosPanel` (list by group, detail, Descargar, Abrir when `canOpenInTab`); wire route component.
- [x] B2.3 RED/GREEN: open path uses `URL.createObjectURL` + `window.open(..., 'noopener,noreferrer')` + revoke; no `iframe`/`object`/`embed` in component tree (lint or unit assert).

### Phase B3: Frontend verification gate

- [x] B3.1 Run Verification · Frontend commands; keep Vitest floors 78/73/76/79.
- [x] B3.2 Manual smoke (optional, note if skipped): login operador → `/admin/documentos` against local API with seeded files.

---

## PR-C — Ops / docs

### Phase C0: Compose prod sample + backup

- [x] C0.1 Document/add `consorcio-documentos` volume + `/app/documentos` mounts on backend in `docker-compose.prod.yml` (sample; box edited by hand).
- [x] C0.2 Add volume to `backup-volumes` mounts; document `BACKUP_SOURCES` must include `/app/documentos` in `scripts/backup_volumes.sh` header/example.

### Phase C1: Runbook

- [x] C1.1 Write `docs/runbooks/documentos-box.md`: rsync from private clone → box path; permissions 0755/0644; deploy order (API+rsync before FE); remind owner to delete Cloudflare Pages project `tramites-consorcio`; note Wave 2–3 roadmap pointer to `openspec/changes/documentos/proposal.md`.
- [x] C1.2 Cross-link from `docs/ROADMAP.md` or RUNBOOK index if one exists (minimal).

### Phase C2: Ops verification

- [x] C2.1 Grep/contract: prod compose sample mentions `documentos`; runbook exists; no confidential binaries in git (`git status` / `git check-ignore` sanity).

---

## Mutation targets (light)

| Module | Target | Note |
|---|---|---|
| `service.resolve_archivo_path` | Jail bypass / wrong prefix | Prefer explicit unit tests over full cosmic-ray budget |
| `mimeActions.canOpenInTab` | HTML accidentally openable | Vitest table |

No new mutation score floor beyond existing CI gates.

---

## Verification

### Backend (from `gee-backend/`)

```bash
ruff check app/domains/documentos tests/new/test_documentos_schemas.py tests/new/test_documentos_catalog.py tests/new/test_documentos_jail.py tests/new/test_documentos_router.py
ruff format --check app/domains/documentos tests/new/test_documentos_*.py
mypy app/domains/documentos
pytest tests/new/test_documentos_schemas.py tests/new/test_documentos_catalog.py tests/new/test_documentos_jail.py tests/new/test_documentos_router.py tests/new/test_auth_gates.py tests/new/test_admin_frontend_contracts.py -q
pytest tests/test_deploy_box_script.py tests/test_ci_workflow_contracts.py tests/test_infra_v6_contracts.py -q
```

(Adjust infra test paths if filenames differ slightly on `main` — discover with `fd 'test_.*infra|test_ci_workflow|test_deploy_box' tests` before A4.)

### Frontend (from `consorcio-web/`)

```bash
npx tsc --noEmit
npx vitest run tests/unit/cloudflareRedirects.test.ts tests/unit/documentosMimeActions.test.ts tests/unit/DocumentosPanel.test.tsx
npx vitest run --coverage
```

(`DocumentosPanel.test.tsx` name may match final component path; keep coverage floors.)

### Forbidden without explicit user auth

- Full `npm run build` / Docker image build / `deploy-box.sh` / rsync to prod / Pages delete.

---

## Known environmental failures

| Issue | Impact | Handling |
|---|---|---|
| TestClient role fixtures may differ (operador vs admin-only helpers) | Ciudadano 403 tests | Reuse patterns from finanzas/padron auth tests; if no ciudadano fixture, add minimal one in documentos router tests only |
| Private corpus not on CI runners | Catalog tests must not read `/home/javier/programacion/tramites-consorcio` in CI | Catalog is **in-repo metadata**; A1.2 authored on laptop from private index, committed as code; CI asserts on committed catalog only |
| Box compose ≠ git | PR-C cannot “deploy” mounts | Runbook states operator applies on box |
| GEE/IDECOR live tests | Unrelated | Do not enable `GEE_LIVE` / `IDECOR_LIVE` for this change |
| Vitest coverage flake under parallel load | Rare | Re-run focused suite once before claiming failure |

---

## Out of scope (do not schedule)

Upload UI, Alembic, RAG ingest, AI editor, deleting Pages project (remind only), modifying Trámites contracts, embedding PDF viewers.
