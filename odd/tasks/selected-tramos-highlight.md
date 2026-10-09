# Multi-select tramos + map highlight

## Goal

Ctrl/⌘-click accumulates LineString tramos in the InfoPanel. Selected lines are highlighted on the 2D map. Plain click still replaces. Close/clear removes the highlight.

## Tasks

- [x] T1: `mergeAdditiveFeatures` + tests (toggle on same key)
- [x] T2: idle click uses additive merge; miss+Ctrl keeps selection
- [x] T3: MapLibre highlight layer for selected LineString/MultiLineString

## Non-goals

- ficha-canal stays single canal
- No 25 km profile ceiling change
- No InfoPanel layout rewrite
