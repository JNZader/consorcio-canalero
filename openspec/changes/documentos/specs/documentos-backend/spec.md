# documentos-backend Specification

## Purpose

Authenticated, operator-only HTTP API that exposes a **code-defined** catalog of
Consorcio administrative dossiers and serves their binary attachments from a
jailed `documentos_root` on the box. No database. No upload. Confidential files
MUST NOT be served without Bearer auth.

## Decisions locked (from Propose D1–D6)

- `documentos_root` defaults to `/app/documentos` (dedicated volume).
- Catalog references only the files that are synced; preview PNGs are out of v1.
- Binary responses use `StreamingResponse` with `Content-Disposition: attachment`.
- All Wave-1 catalog rows carry `clasificacion: "privado"` (reclassify before any
  future RAG ingest — out of scope here).
- List returns dossier summaries; file descriptors appear on detail only.

## Requirements

### Requirement: Domain isolation from Trámites

The Documentos capability MUST live under a new domain
`gee-backend/app/domains/documentos/` with router prefix `/documentos` mounted at
`/api/v2`. It MUST NOT modify `TramiteCreate`, `TramiteResponse`,
`/api/v2/tramites/*`, or admin Trámites frontend contracts.

#### Scenario: Trámites contracts unchanged

- GIVEN the Documentos domain is registered
- WHEN `tests/new/test_admin_frontend_contracts.py` runs
- THEN Trámites payload round-trips still pass without Documentos fields

### Requirement: Code catalog without persistence

The catalog MUST be defined in repository code (Python module and/or checked-in
JSON under the domain). The API MUST NOT read dossier metadata from SQLAlchemy
models or Alembic migrations. Adding a dossier in Wave 1 REQUIRES a code change
and deploy.

#### Scenario: No migration required

- GIVEN a fresh database at current `alembic head`
- WHEN Documentos endpoints are exercised
- THEN no new tables are required and `alembic upgrade` is not part of deploy

### Requirement: Opaque identifiers

Dossier ids and file ids MUST be opaque stable strings (e.g. catalog keys such as
`codist-p-ach` / generated file keys). Request paths MUST NOT embed filesystem
paths or original filenames. Logs and error bodies MUST NOT echo resolved
absolute paths or relative storage paths to clients.

#### Scenario: Download URL uses opaque ids only

- GIVEN a dossier `codist-p-ach` with an attached PDF
- WHEN the client requests the file
- THEN the path matches `/api/v2/documentos/{dossier_id}/archivo/{file_id}`
- AND neither the path nor a successful JSON error carries `p-ach.pdf` as a path
  segment

### Requirement: Catalog list endpoint

`GET /api/v2/documentos` MUST require an authenticated user with role `operador`
or `admin` (`require_operator` / `require_admin_or_operator`). It MUST return
HTTP 200 with a JSON array (or `{ items: [...] }` wrapper consistent with nearby
admin list style chosen in Design) of dossier **summaries**.

Each summary MUST include at least:

| Field | Rule |
|---|---|
| `id` | opaque dossier id |
| `titulo` | non-empty string |
| `group` | catalog group key (`notas`, `cidi`, `codist`, `conflictos`, `informes`, `informes-tecnicos`, `cruces`, …) |
| `expediente` | string (may be empty only if source catalog lacks it — prefer always present) |
| `badge` | optional string |
| `fecha` | optional string as in source catalog |
| `clasificacion` | MUST be `"privado"` in Wave 1 |
| `file_count` | integer ≥ 0 |

Summaries MUST NOT include file relative paths or file descriptors.

Optional query `group` MAY filter by exact group key; unknown group MUST yield an
empty list (HTTP 200), not 404.

#### Scenario: Operator lists dossiers

- GIVEN a valid operator Bearer token and a catalog with 25 dossiers
- WHEN `GET /api/v2/documentos`
- THEN HTTP 200 and exactly 25 summaries
- AND every item has `clasificacion == "privado"`
- AND no item contains a `path` or `files` array

#### Scenario: Unauthenticated list rejected

- GIVEN no Authorization header
- WHEN `GET /api/v2/documentos`
- THEN HTTP 401
- AND this path is covered by `tests/new/test_auth_gates.py`

#### Scenario: Ciudadano list forbidden

- GIVEN a valid ciudadano Bearer token
- WHEN `GET /api/v2/documentos`
- THEN HTTP 403

#### Scenario: Filter by group

- GIVEN catalog groups include five `codist` dossiers
- WHEN `GET /api/v2/documentos?group=codist`
- THEN HTTP 200 with exactly those five summaries

### Requirement: Catalog detail endpoint

`GET /api/v2/documentos/{id}` MUST require operator+. On unknown id it MUST
return HTTP 404 without revealing whether a similarly named file exists on disk.

The detail payload MUST include the summary fields plus `files`: an array of
descriptors, each with at least:

| Field | Rule |
|---|---|
| `id` | opaque file id |
| `nombre` | display / download filename (basename only) |
| `mime` | IANA media type |
| `bytes` | optional size if known at catalog build time; else omitted |
| `accion` | `"download"` \| `"open_or_download"` — see frontend spec; backend MAY omit and let FE decide by mime |

`files` MUST NOT include storage-relative paths.

#### Scenario: Detail with attachments

- GIVEN dossier `codist-p-sar` has one PDF in the catalog
- WHEN `GET /api/v2/documentos/codist-p-sar`
- THEN HTTP 200
- AND `files` length ≥ 1
- AND each file has opaque `id`, `nombre`, `mime`
- AND no file object contains a `path` field

#### Scenario: Unknown dossier

- GIVEN id `does-not-exist`
- WHEN `GET /api/v2/documentos/does-not-exist`
- THEN HTTP 404

### Requirement: Authenticated file download

`GET /api/v2/documentos/{id}/archivo/{file_id}` MUST require operator+.

On success it MUST return the file bytes via `StreamingResponse` with:

- Correct `Content-Type` from the catalog mime (fallback `application/octet-stream`)
- `Content-Disposition: attachment; filename="<nombre>"` using the catalog display
  name (ASCII/filename* per existing tramites export style is acceptable)
- HTTP 200

The handler MUST resolve the catalog entry to a relative path, join it under
`settings.documentos_root`, and enforce a **realpath jail**:

1. `root = realpath(documentos_root)`
2. `candidate = realpath(join(root, relative_path))`
3. Reject unless `candidate == root` or `candidate` starts with `root + sep`

Missing files on disk MUST yield HTTP 404 (catalog entry exists but blob absent).
Unknown dossier id or file id MUST yield HTTP 404.

The endpoint MUST NOT accept query parameters that carry tokens (`access_token`
or similar). Auth is Bearer header only.

#### Scenario: Operator downloads PDF

- GIVEN operator auth and file present under `documentos_root`
- WHEN `GET /api/v2/documentos/codist-p-ach/archivo/{file_id}`
- THEN HTTP 200
- AND `Content-Type` is `application/pdf`
- AND `Content-Disposition` starts with `attachment`
- AND body length matches the file on disk

#### Scenario: Path traversal rejected

- GIVEN a catalog bug or test double that would resolve to `../etc/passwd`
- WHEN the download handler resolves the path
- THEN the request fails closed (HTTP 400 or 404)
- AND no bytes outside `documentos_root` are read

#### Scenario: Unauthenticated download rejected

- GIVEN no Authorization header
- WHEN `GET /api/v2/documentos/codist-p-ach/archivo/{any}`
- THEN HTTP 401
- AND covered by `test_auth_gates.py`

#### Scenario: Ciudadano download forbidden

- GIVEN ciudadano Bearer token
- WHEN the download endpoint is called
- THEN HTTP 403

### Requirement: Startup and configuration

Settings MUST expose `documentos_root: str` defaulting to `/app/documentos`.
Application startup MUST `os.makedirs(documentos_root, exist_ok=True)` analogous
to `uploads_root`, so a missing directory does not crash workers on first
request with an unclear error.

#### Scenario: Root created at startup

- GIVEN `documentos_root` points to a missing directory
- WHEN the app starts
- THEN the directory exists before requests are served

### Requirement: Open MIME policy (server)

The backend MUST serve every catalogued mime as **attachment** download. It MUST
NOT set `Content-Disposition: inline` in Wave 1 (frontend decides blob-tab open
for PDF/JPG after download). Serving `.html` / `.kmz` / `.docx` as attachment is
REQUIRED when those files are in the catalog.

#### Scenario: HTML served as attachment

- GIVEN a catalog file with `mime` `text/html`
- WHEN downloaded
- THEN `Content-Disposition` is `attachment` (not `inline`)

### Requirement: API contract checks

Contract tests MUST assert:

1. List/detail JSON field names and types for a fixture catalog subset.
2. Download headers (`content-type`, `content-disposition` disposition=attachment).
3. 401 matrix entries for list, detail, and download in `test_auth_gates.py`.
4. 403 for ciudadano on list and download.
5. Jail unit tests with tmp_path without needing the real corpus.

## Non-requirements (explicit)

- Upload, DELETE, PATCH, or admin mutation of catalog via API.
- Streaming range requests / resumable downloads.
- Ingest into `conocimiento` / RAG tables.
- Audit-log row per download (optional follow-up; not Wave 1 MUST).
- Caddy configuration changes.
