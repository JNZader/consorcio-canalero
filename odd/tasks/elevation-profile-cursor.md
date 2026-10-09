# Elevation profile map cursor

## Goal

When the operator hovers the GLO-30 elevation chart, mark the matching point on the selected LineString on the 2D map (Google Earth analog).

## Tasks

- [x] T1: `pointAlongLineString` + unit tests (existing `@turf/distance`, no new package)
- [x] T2: Chart `onHoverDistanceM` via Recharts `onMouseMove` / `onMouseLeave`; tests
- [x] T3: Thread callback InfoPanel → MapUiPanels → MapaMapLibre; MapLibre GeoJSON cursor layer; clear on leave/close

## Non-goals

- No API lon/lat on samples
- No `@turf/along` dependency
- No 3D terrain marker
- No compose/deploy
