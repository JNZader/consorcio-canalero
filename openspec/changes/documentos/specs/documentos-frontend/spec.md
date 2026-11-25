# documentos-frontend Specification

## Purpose

Admin UI for **Documentos**: list and inspect the code catalog, download
attachments with Bearer auth, and open PDF/JPG in a new tab via blob URLs —
without embedding viewers and without putting tokens in URLs.

## Decisions locked (from Propose D1–D6)

- Nav label **Documentos** (never “Trámites”).
- Route `/admin/documentos`.
- Downloads via `fetchAuthenticatedFile` + temporary anchor click.
- PDF/JPG may open in a new tab with `URL.createObjectURL` + `window.open`;
  `.html` / `.kmz` / `.docx` (and any other non-PDF/JPG) download only.
- Preview PNGs are not shown as catalog attachments in Wave 1.

## Requirements

### Requirement: Admin route and SPA lockstep

The app MUST register a protected admin child route at `/admin/documentos` in
`consorcio-web/src/routeTree.gen.tsx`. The same path MUST be listed in
`consorcio-web/public/_worker.js` `SPA_ROUTES`. The unit test
`tests/unit/cloudflareRedirects.test.ts` MUST keep SPA_ROUTES in lockstep with
the router.

#### Scenario: Deep link works on Pages

- GIVEN the worker SPA_ROUTES includes `/admin/documentos`
- WHEN a logged-in operator opens `/admin/documentos` as a full navigation
- THEN the Documentos page renders (not a static 404 from Pages)

#### Scenario: Lockstep test fails if route missing from worker

- GIVEN `/admin/documentos` exists in `routeTree.gen.tsx` but not in `SPA_ROUTES`
- WHEN `cloudflareRedirects` unit tests run
- THEN the suite fails

### Requirement: Navigation entry

`AdminLayout` MUST add a **Documentos** item under the Gestión section, distinct
from **Trámites**. The item MUST be visible to `operador` and `admin` (same
visibility model as Trámites — not admin-only like Consultas normativas).

#### Scenario: Operator sees Documentos in nav

- GIVEN an authenticated operador session
- WHEN the admin shell renders
- THEN a nav link labeled `Documentos` targets `/admin/documentos`
- AND the existing `Trámites` link remains unchanged

### Requirement: List view

The Documentos page MUST load `GET /api/v2/documentos` with the shared API client
(Bearer). It MUST show dossiers grouped by `group` (or an equivalent filterable
list). Loading, empty, and error states MUST be visible.

#### Scenario: List renders 25 dossiers

- GIVEN the API returns 25 summaries
- WHEN the page loads
- THEN the UI presents all 25 (grouped or filterable)
- AND does not call download endpoints until the user acts

#### Scenario: List error surfaced

- GIVEN the API returns 500
- WHEN the page loads
- THEN an error message is shown and no false empty-success state is claimed

### Requirement: Detail view

Selecting a dossier MUST load `GET /api/v2/documentos/{id}` (or use list+detail
as designed) and show metadata (`titulo`, `expediente`, `badge`, `fecha`,
`clasificacion`) and the `files` list with actions.

#### Scenario: Detail shows files without storage paths

- GIVEN detail JSON includes files with `id`, `nombre`, `mime`
- WHEN detail renders
- THEN each file shows `nombre` and action controls
- AND no storage path string is displayed

### Requirement: Authenticated download

Download MUST call `fetchAuthenticatedFile` against
`/documentos/{id}/archivo/{file_id}` with `LONG_TIMEOUT`. The client MUST NOT
put `access_token` (or any secret) in the URL query string. After receiving the
blob, the UI MUST trigger a download via a temporary `<a download>` and revoke
the object URL.

#### Scenario: PDF download via blob anchor

- GIVEN operator session and a PDF file descriptor
- WHEN the user activates Descargar
- THEN `fetchAuthenticatedFile` is invoked with the opaque ids path
- AND a download anchor is clicked with a blob URL
- AND the object URL is revoked after use

#### Scenario: Token never in URL

- GIVEN any Documentos download
- WHEN the request is built
- THEN the request URL has no `access_token` query param
- AND existing `apiCoreHelpers` tests that pin this behavior remain green

### Requirement: Open in new tab (PDF/JPG only)

For files whose `mime` is `application/pdf` or an image type
`image/jpeg` / `image/jpg` / `image/png` (PNG only if ever catalogued — Wave 1
previews omitted), the UI MAY offer **Abrir** which:

1. Fetches via `fetchAuthenticatedFile` (same as download)
2. Creates a blob URL
3. Opens it with `window.open(url, '_blank', 'noopener,noreferrer')`
4. Revokes the URL after a short delay

The UI MUST NOT use `<iframe>`, `<object>`, or `<embed>` for Documentos.

For `text/html`, `application/vnd.google-earth.kmz`, Keyhole MIME variants,
`application/vnd.openxmlformats-officedocument.wordprocessingml.document`,
`application/msword`, `.tex` sources, and any other non-PDF/non-image type, the
UI MUST offer download only (no Abrir).

#### Scenario: PDF can open in new tab

- GIVEN mime `application/pdf`
- WHEN the user activates Abrir
- THEN a new browsing context receives a blob URL
- AND no iframe is mounted

#### Scenario: KMZ is download-only

- GIVEN mime indicating KMZ/KML package
- WHEN detail renders
- THEN only Descargar is offered (no Abrir)

#### Scenario: HTML is download-only

- GIVEN mime `text/html`
- WHEN detail renders
- THEN only Descargar is offered

### Requirement: CSP and framing assumptions

The frontend MUST assume Pages CSP keeps `object-src 'none'` and
`X-Frame-Options: DENY`. Documentos UI MUST NOT depend on embedding remote or
blob documents in-frame.

#### Scenario: No object/embed in Documentos tree

- GIVEN the Documentos React components
- WHEN reviewed / tested
- THEN they do not render `iframe`/`object`/`embed` for attachments

### Requirement: Auth gate UX

If the session lacks operator privileges, the route MUST behave like other admin
management routes (redirect to login or forbidden pattern already used by
Trámites). The page MUST NOT attempt anonymous downloads.

#### Scenario: Logged-out deep link

- GIVEN no session
- WHEN navigating to `/admin/documentos`
- THEN the user is sent through the existing admin auth gate (login / forbidden)
- AND no Documentos API call succeeds anonymously from the UI

### Requirement: Coverage floors

New Documentos UI/tests MUST NOT drop Vitest thresholds below statements 78 /
branches 73 / functions 76 / lines 79. At least one unit test MUST cover the
download helper path (mock `fetchAuthenticatedFile`) and one MUST cover
open-vs-download mime branching.

#### Scenario: Mime branching unit test

- GIVEN mime `application/pdf` and mime `application/vnd.google-earth.kmz`
- WHEN the action-availability helper runs
- THEN PDF allows open+download and KMZ allows download only

### Requirement: Naming and copy

User-visible strings MUST use **Documentos**. They MUST NOT reuse the word
“Trámites” for this section’s title, nav, or empty states, to avoid confusing
the workflow domain with the confidential file bodega.

#### Scenario: Nav labels distinct

- GIVEN admin Gestión nav
- WHEN rendered
- THEN both `Trámites` and `Documentos` appear as separate items

## Non-requirements (explicit)

- WYSIWYG / AI note editor.
- Upload dropzone.
- Client-side full-text search over PDF contents.
- Porting the static `tramites-consorcio` `index.html` visual design.
- Showing HTML `formattedPreview` from the private index (optional later).
