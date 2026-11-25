# Design: Documentos (Wave 1)

## Technical approach

Add a read-only screaming-architecture domain that serves a **code catalog** of
25 administrative dossiers and streams attachment bytes from a jailed directory
on the box. The frontend gets a new admin page that lists/details dossiers and
downloads via the existing Bearer + blob pattern.

No Alembic. No upload. No RAG. No editor. Waves 2–3 remain documentation only
(see Proposal roadmap); this design only ensures the catalog identity contract
is stable enough to cite later.

## Architecture decisions

| Topic | Choice | Rejected | Rationale |
|---|---|---|---|
| Persistence | Code catalog (`catalog.py` + optional `catalog.json` imported by it) | Postgres / Alembic | Explicit Wave-1 NON-goal; 25 rows; deploy-to-update is acceptable |
| Domain name / routes | `documentos` / `/api/v2/documentos` / `/admin/documentos` | Reuse `tramites` | Existing workflow domain + contracts must stay untouched |
| Storage root | `settings.documentos_root` default `/app/documentos` + volume `consorcio-documentos` | Nest under `/app/uploads/documentos` | Separates ACL/backup from denuncia photos; same jail pattern |
| Binary response | `StreamingResponse` + `Content-Disposition: attachment` | `FileResponse`; `inline`; `main.py` photo `Response` | Matches trámites/reuniones exports; FE owns blob-tab open |
| Path safety | Opaque ids → catalog relative path → `realpath` prefix jail | Pass path in URL; trust join alone | Filename never in URL/logs to clients; blocks `..` |
| List envelope | `{ "items": [DocumentoResumen, ...] }` (no pagination) | `PaginatedResponse` | Fixed ~25 rows; pagination would be ceremony |
| Detail files | Files only on `GET /{id}` | Files embedded in list | Smaller list; matches D8 |
| Clasificación | All rows `"privado"` | Mix institucional now | Fail-closed for future RAG egress; reclassify in a later change |
| Sync set | Catalog-referenced paths only | Whole `docs/` + `previews/` | Attack/backup surface; D2/D3 |
| PDF open | FE blob + `window.open` after authenticated fetch | iframe / object / inline disposition | CSP `object-src 'none'` + `X-Frame-Options: DENY` |
| PR split | backend → frontend → ops/docs | Monolith PR | Deploy skew + >400 LOC; D5/D6 |
| Auth | `require_admin_or_operator` lazy like tramites | New middleware | One pattern; ciudadano → 403 |

## Catalog model

Source of truth for content: private `tramites-consorcio/index.html` (25 `id`s).
Implementation stores a frozen structure in-repo (public metadata only — **no
file bytes**).

```text
DocumentoCatalogo
  id: str                 # e.g. "codist-p-ach" — opaque, stable
  titulo: str
  group: str              # notas | cidi | codist | conflictos | …
  group_label: str | None
  expediente: str
  badge: str | None
  fecha: str | None
  clasificacion: Literal["privado"]  # Wave 1
  destinatario: str | None           # DNV | APRHI | Castelló | Co.Di.St. | …
  autores: list[str] | None
  files: list[ArchivoCatalogo]

ArchivoCatalogo
  id: str                 # opaque file key, unique within dossier (or globally)
  nombre: str             # basename for Content-Disposition / UI
  mime: str
  relative_path: str      # ONLY server-side; never in API JSON
  bytes: int | None       # optional, filled at catalog build time
```

API schemas expose summaries/details **without** `relative_path`.

File id scheme (locked): `{dossier_id}__{stable_slug}` where `stable_slug` is a
slug of the basename (e.g. `codist-p-ach__p-ach-pdf`). Must be unique per
dossier; global uniqueness preferred for simpler logging.

### Groups (from exploration)

`notas` (7), `cidi` (6), `codist` (5), `conflictos` (3), plus
`informes` / `informes-tecnicos` / `cruces` for the remaining ids — exact
membership copied from the private index when building the catalog module.

## API design

Prefix: `/api/v2/documentos` via `APIRouter(prefix="/documentos", tags=["documentos"])`.

| Method | Path | Auth | Success |
|---|---|---|---|
| GET | `` | operator+ | `{ items: DocumentoResumen[] }` |
| GET | `/{id}` | operator+ | `DocumentoDetalle` (includes `files[]`) |
| GET | `/{id}/archivo/{file_id}` | operator+ | `StreamingResponse` attachment |

Query: optional `group` on list (exact match; unknown → empty `items`).

Errors: `401` unauthenticated, `403` wrong role, `404` unknown id / missing
blob / jail failure treated as not-found (do not leak path), `400` only if we
distinguish malformed ids — prefer `404` for jail misses to avoid oracle.

### Download resolution algorithm

```text
entry = catalog.get_dossier(id) or 404
file  = entry.file_by_id(file_id) or 404
root  = realpath(settings.documentos_root)
cand  = realpath(join(root, file.relative_path))
if cand != root and not cand.startswith(root + sep): 404
if not isfile(cand): 404
stream file; media_type=file.mime; Content-Disposition=attachment; filename=file.nombre
```

Open file in binary read; wrap in iterator or `File`-like for
`StreamingResponse`. Do not load entire file into a BytesIO unless tests need it
— prefer streaming from disk (files ≤ ~5 MB either way).

## Backend module layout

```text
gee-backend/app/domains/documentos/
  __init__.py
  catalog.py          # data + getters (no I/O of bytes)
  schemas.py          # Pydantic response models
  service.py          # list/detail + resolve_path / open_stream
  router.py           # HTTP + Depends(require_operator)
  # no models.py, no repository.py
```

`config.py`: `documentos_root: str = "/app/documentos"`.
`main.py`: `os.makedirs(settings.documentos_root, exist_ok=True)` next to uploads.
`api/v2/router.py`: `include_router(documentos_router)`.

## Frontend module layout

```text
consorcio-web/src/
  routeTree.gen.tsx              # adminDocumentosRoute
  components/admin/AdminLayout.tsx  # nav item Documentos
  components/admin/management/DocumentosPanel.tsx  # or documentos/
  lib/api/documentos.ts          # typed list/detail helpers (optional thin)
  lib/documentos/mimeActions.ts  # pure: canOpenInTab(mime) → boolean
public/_worker.js                # SPA_ROUTES += '/admin/documentos'
```

Download/open:

1. `fetchAuthenticatedFile(`/documentos/${id}/archivo/${fileId}`, { timeout: LONG_TIMEOUT })`
2. Download: `<a download={nombre}>`; revoke.
3. Open (PDF/JPEG only): `window.open(blobUrl, '_blank', 'noopener,noreferrer')`; revoke after delay.

`canOpenInTab`: true iff mime is `application/pdf` or `image/jpeg` / `image/jpg`
(and `image/png` if ever present — previews omitted so unlikely).

## Ops / box

Dev compose + prod **sample** compose:

- Volume `consorcio-documentos` → `/app/documentos` on `backend` (and any
  service that might serve the API — worker not required for Wave 1).
- `uploads-init`-style ownership optional; document `chown`/`chmod 0755` dirs /
  `0644` files (GEE credentials precedent in `docs/runbooks/infra-cicd-v6.md`).

Rsync (operator laptop → box), conceptual:

```bash
rsync -av --relative \
  /home/javier/programacion/tramites-consorcio/./visor_assets/... \
  consorcio-prod:/path/to/documentos-data/
```

Exact mapping (catalog `relative_path` ↔ on-disk layout) is fixed when the
catalog is authored in Apply: prefer preserving `visor_assets/...` and
`docs/...` relative paths under `/app/documentos/` so paths in catalog match the
private tree.

`BACKUP_SOURCES` on the box MUST include `/app/documentos` (colon-separated with
existing uploads/geo). Prod `backup-volumes` service mounts the new volume read-only.

**Deploy order:** PR-A merge + `deploy-box.sh` + rsync → PR-B merge (Pages) →
PR-C docs. Reminder: owner deletes Cloudflare Pages project `tramites-consorcio`.

## Roadmap bridge (non-goals, intentional seams)

| Seam | Wave 1 | Later |
|---|---|---|
| Stable `id` / `file_id` | Required | Citation keys for note editor |
| `clasificacion` field | Always `privado` | Reclassify before RAG ingest |
| `relative_path` private | Server only | Ingest pipeline reads same root or a text extract store |
| Binary ≠ corpus | Enforce in docs/tests comments | Separate ingest change with gates |

Do **not** add RAG hooks, Celery tasks, or editor routes in this change.

## File change map (expected)

### PR-A backend

| File | Action |
|---|---|
| `gee-backend/app/domains/documentos/*` | Create |
| `gee-backend/app/api/v2/router.py` | Include router |
| `gee-backend/app/config.py` | `documentos_root` |
| `gee-backend/app/main.py` | `makedirs` |
| `gee-backend/tests/new/test_documentos_*.py` | Create |
| `gee-backend/tests/new/test_auth_gates.py` | Add paths |
| `docker-compose.yml` | Volume + mount (dev) |

### PR-B frontend

| File | Action |
|---|---|
| `routeTree.gen.tsx`, `_worker.js`, `AdminLayout.tsx` | Route + nav |
| `DocumentosPanel` (+ tests) | UI |
| `mimeActions.ts` (+ unit tests) | Open vs download |
| `cloudflareRedirects.test.ts` | Lockstep |

### PR-C ops/docs

| File | Action |
|---|---|
| `docker-compose.prod.yml` | Sample volume/mounts/backup |
| `docs/runbooks/documentos-box.md` (or under `docs/`) | Rsync, perms, backup, Pages teardown reminder |
| `scripts/backup_volumes.sh` comment / example env | Document `BACKUP_SOURCES` |

## Testing strategy

| Layer | What | How |
|---|---|---|
| Unit BE | Catalog getters, jail accept/reject, missing file → 404 | `tmp_path`, fixture mini-catalog override via monkeypatch |
| Unit BE | Auth 401/403 | `test_auth_gates.py` + role fixtures |
| Unit BE | Download headers | TestClient + small PDF bytes on disk |
| Unit FE | `canOpenInTab` matrix | Vitest table |
| Unit FE | Download triggers fetchAuthenticatedFile | Mock core helper |
| Contract | SPA_ROUTES ↔ routeTree | Existing cloudflare test |
| Regression | Trámites admin contracts | Untouched; must stay green |
| Infra | No Alembic in deploy-box; Dockerfile mkdir string | Existing infra contract tests — do not break |
| Mutation | Optional light targets on jail function | Only if tasks budget allows; not blocking Wave 1 |

### CI commands (Verification will name exact invocations)

```bash
# backend (from gee-backend/)
ruff check app/domains/documentos tests/new/test_documentos_*.py
ruff format --check …
mypy app/domains/documentos
pytest tests/new/test_documentos_*.py tests/new/test_auth_gates.py -q

# frontend (from consorcio-web/)
npx tsc --noEmit
npx vitest run tests/unit/cloudflareRedirects.test.ts tests/unit/**/documentos* tests/unit/**/mimeActions*
```

No full production build unless explicitly authorized.

## Threat matrix

| Threat | Mitigation |
|---|---|
| Unauthenticated read of confidential PDFs | Bearer + `require_operator`; auth_gates CI |
| Path traversal | Opaque ids + realpath jail + unit tests |
| Token in URL / logs | Reuse `fetchAuthenticatedFile`; no query tokens |
| Accidental git publish of binaries | Never copy corpus into public tree; gitignore belt; PR review |
| XSS via HTML attachment inline | Always `attachment`; FE download-only for HTML |
| Clickjacking / embed | Existing DENY / CSP; no iframe in UI |
| Backup omission | PR-C updates BACKUP_SOURCES + mounts |
| Deploy skew (FE before files/API) | Chained PRs + runbook gate |

## Rollback

1. Revert PR-B → UI gone.
2. Revert PR-A → API gone.
3. Box: remove volume mount; files remain until operator deletes.
4. Private repo + Pages (until owner deletes Pages) remain fallback.

## Open questions

- [x] D1–D8 (Propose).
- [x] List envelope = `{ items }` without pagination.
- [x] File id scheme = `{dossier_id}__{basename-slug}`.
- [ ] Exact catalog field transcription from `index.html` (Apply task: build
      `catalog.py` from the 25 ids — mechanical, not a product decision).
