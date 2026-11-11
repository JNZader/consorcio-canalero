# ImageExplorer redesign (full UI)

Objective: ship `odd/docs/image-explorer-redesign.md` as working UI in three mergeable waves. Branch stack from `feat/image-explorer-redesign`. Delivery: ask-on-risk. Runner: vitest.

## Specs

- **S1** — Tabs Escena | Comparar | Detectar; one active job at a time.
- **S2** — Publish tray shows imagen activa and/or par Antes/Después; primary CTA **Abrir en mapa** navigates to `/mapa` and requests the matching view mode (single | comparison).
- **S3** — Preview ≠ published: tray reflects `useSelectedImage` / `useImageComparison` stores.
- **S4** — Event panel can set shared flood/normal dates and deep-link to Detectar; shortlist/pair actions still work.
- **S5** — Detectar is a 3-step flow (crecida → referencia → método) with human copy; no start_date/end_date in UI; on success fills comparison and tray.
- **S6** — Comparar uses Antes/Después slots (not Izquierda/Derecha as primary labels).
- **S7** — Focused tests for tray navigation hint, detect prefill, and compare slot labels.

## Tasks

- [x] T1 Publish tray + map preferred-view hint + panel tabs shell — S1 S2 S3 — wave1
- [x] T2 Events as shared shortcuts (select → dates, Detectar CTA) — S4 — wave2
- [x] T3 Detect wizard + Comparar Antes/Después + copy cleanup — S5 S6 S7 — wave3

## Log

- **L1** (2026-11-09): User: finish all code; merge later in order.
- **L2** (2026-11-09): Implemented full UI on `feat/image-explorer-redesign`. Vitest focused suite green (PublishTray, FloodAnalysis, ExtremeEvents, mapPreferredView, InfoPanels, geeFloodAnalysis).
- **L3** (2026-11-09): Closed gaps — `Usar par en Comparar` (event → tray) + Comparar tab CTAs `Usar preview como Antes/Después`. Tests 48 green. PR #691 body update; no merge.
