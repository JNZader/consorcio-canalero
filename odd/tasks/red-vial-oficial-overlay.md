# red-vial-oficial-overlay

## Objective
Staff-only overlay of the live IDECOR/Vialidad road catalog clipped to the CC contour, matched against our `red_vial` 380.

## Finding (2026-09-22 WFS)
- Provincial official inside zona: 261 tramos / 548.9 km, **all** already in our padron (20 m / 70%).
- National official inside zona: 78 tramos / 90.2 km **missing** from our padron (AU9 + RN1V09).
- Our 380 has no extra vs official provincial.

## Tasks
- [x] Fetch WFS bbox, clip zona, write `consorcio-web/public/capas/red_vial_oficial_clip.geojson`
- [x] Staff Capas toggle: orange = `falta_en_padron`, muted green dashed = `en_padron`
- [x] Do not merge into `red_vial` (cruces/relevamiento FK). 2D only.
