```yaml
schema: gentle-ai.verify-result/v1
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
change: documentos
wave: 1
mode: interactive-sdd-manual
```

# Verification Report — Documentos (Wave 1)

**Branch**: `feat/documentos`  
**Base**: `origin/main` @ `c012e893`  
**When**: 2026-11-25 (local laptop)  
**Build**: full `npm run build` / Docker **not** run (gated; no user auth for build).

## Completeness

| Metric | Value |
|--------|-------|
| Tasks A0–A4 / B0–B3 / C0–C2 | All checked in `tasks.md` |
| Specs | `documentos-backend` + `documentos-frontend` authored |
| Confidential PDF/DOCX bytes in git | None observed (`git status` / no binary matches) |
| Manual FE smoke (login → download) | **Skipped** (W1) — needs box corpus + local API |

## Build & Tests

### Backend (project venv)

```text
PY=/home/javier/programacion/consorcio-canalero/gee-backend/venv/bin/python
cd gee-backend
$PY -m ruff check app/domains/documentos tests/new/test_documentos_{schemas,catalog,jail,router}.py
→ All checks passed
$PY -m ruff format --check … (same paths)
→ 9 files already formatted
$PY -m mypy app/domains/documentos
→ Success: no issues found in 5 source files
$PY -m pytest tests/new/test_documentos_schemas.py \
  tests/new/test_documentos_catalog.py \
  tests/new/test_documentos_jail.py \
  tests/new/test_documentos_router.py \
  tests/new/test_auth_gates.py \
  tests/new/test_admin_frontend_contracts.py -q
→ 55 passed in 9.51s (exit 0)
```

Note: brew-system `pytest` lacks sqlalchemy; gates must use the app venv above.

### Infra / deploy-box

```text
$PY -m pytest scripts/tests/test_deploy_box_script.py \
  gee-backend/tests/test_ci_workflow_contracts.py \
  gee-backend/tests/test_infra_v6_contracts.py -q
→ 94 passed in 4.40s (exit 0)
```

### Frontend

```text
cd consorcio-web
npx tsc --noEmit
→ exit 0
npx vitest run tests/unit/cloudflareRedirects.test.ts \
  tests/unit/documentosMimeActions.test.ts \
  tests/unit/documentosDownload.test.ts
→ 3 files, 23 passed (exit 0)
npx vitest run --coverage
→ Statements 79.92% / Branches 73.9% / Functions 78.55% / Lines 81.75%
  (floors 78 / 73 / 76 / 79) — exit 0
```

### Ops greps (PR-C)

- `docker-compose.prod.yml` defines `documentos-data` / `consorcio-documentos` and mounts `/app/documentos` on backend, uploads-init, backup-volumes.
- `scripts/backup_volumes.sh` default `BACKUP_SOURCES` includes `/app/documentos`.
- `docs/runbooks/documentos-box.md` exists (rsync, perms, deploy order, Pages teardown reminder).
- `docs/ROADMAP.md` points at OpenSpec + runbook.

## Spec spot-check

| Requirement (Wave 1) | Evidence |
|----------------------|----------|
| Catalog in code, 25 dossiers, all `privado` | `test_documentos_catalog.py` green |
| No `relative_path` on public schemas | `test_documentos_schemas.py` green |
| realpath jail | `test_documentos_jail.py` green |
| Operator list/detail/download + attachment | `test_documentos_router.py` green |
| Unauthenticated → 401 | `TestDocumentosAuthGates` green |
| SPA `/admin/documentos` lockstep | `cloudflareRedirects` + routeTree + `_worker.js` |
| PDF/JPEG open-in-tab; HTML/KMZ download-only | `documentosMimeActions` + download helpers |
| Trámites contracts untouched | `test_admin_frontend_contracts` green |

## Warnings (non-blocking)

| ID | Note |
|----|------|
| W1 | Manual smoke skipped — operator login + seeded `/app/documentos` not exercised this session |
| W2 | Live box compose is hand-edited; git `docker-compose.prod.yml` is sample only (runbook) |
| W3 | Reminder for owner: delete Cloudflare Pages project `tramites-consorcio` after admin is live (not automated) |
| W4 | PR-A catalog metadata will exceed 400-line review budget; accepted as chained-PR slice with `size:exception` for authored catalog dump |

## Delivery next

Stacked PRs to `main` (design D6): **PR-A backend → PR-B frontend → PR-C ops/docs**.
