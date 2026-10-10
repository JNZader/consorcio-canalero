# rainfall-imagery-shortlist

Worktree: `/home/javier/programacion/worktrees/consorcio-imagery-shortlist`
Branch: `feat/rainfall-imagery-shortlist` (from `origin/main` `4dfc9728`)

## Goal

Staff-only pipeline: for each imagery-eligible extreme-rainfall event, inventory S2/S1/L8 scenes in a small window, score them (time + scene cloud metadata + sensor), persist top 3. No public timeline. No ML. No zonal cloud reduce (disclosed as scene-level). No auto-publish.

## Tasks

- [x] T1 — Pure ranker + tests (RED/GREEN).
- [x] T2 — Table + replace persist + GET `/geo/gee/images/historic-floods/{id}/candidates` (operator, no GEE).
- [x] T3 — Hand-run CLI with injectable lister; GEE lister isolated. Work-unit commit.

## Non-goals

- Cloud fraction over the zone (reduceRegion)
- Auto-publish to the public map
- Frontend "Probar este" (follows #425)
- Sentinel-1 water delta vs dry scene
