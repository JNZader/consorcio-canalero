# explorer-rainfall-imagery

Worktree: `/home/javier/programacion/worktrees/consorcio-explorer-rainfall`
Branch: `feat/explorer-rainfall-imagery` (from `origin/main` `4dfc9728`)

## Goal

Operator bridge in Image Explorer: pick a CHIRPS extreme-rainfall event → search GEE imagery → publish with existing "Usar esta imagen". Catalog stays private. No public timeline. No new libraries.

## Tasks

- [x] T1 — Event cards show imagery candidacy, explicit "Buscar imagen", hide non-candidates by default, CHIRPS disclosure stays visible. Tests first.
- [x] T2 — Place the event list under the calendar (left column). Result bar keeps publish/compare. Do not change D9 severity palette (`extrema` on the wire still yellow; backend remaps `extrema→alta`).
- [ ] T3 — Focused vitest on ImageExplorerInfoPanels + controller. Work-unit commit.

## Non-goals

- Public R8 play/slider
- Daily rainfall rasters on the map
- Backend catalog/detector changes
- New npm packages
- Remapping D9 badge colours
