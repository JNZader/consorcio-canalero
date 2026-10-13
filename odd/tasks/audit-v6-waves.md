# audit-v6-waves

Campaign from `auditoria-v6.pdf` (12/10/2026, base `6f76b97`). One theme per PR. MapLibre 6 is a separate worktree; do not share `MapaMapLibre.tsx` with MAP-07 until the bump lands or MAP-07 merges first.

## Wave A (parallel, no MapLibre API)

- [x] FE-01 — #479
- [x] UI-07 + MAP-06 — #482

## Wave B (after A, or MAP-07 before MapLibre)

- [x] MAP-07 + MAP-13 — #483

## Wave C

- [x] MapLibre 6 — #484 pin 6.14.0 (`feat/map-ux-maplibre-6`)

## Wave D (this branch `feat/audit-v6-wave-d`, stacked on C)

- [ ] MAP-01 + MAP-01b — full-buffer soils PMTiles (no Range)
- [ ] BE-01 — exact public GET allowlist + Cache-Control + no 429 retry

## Out

CODE-02, UX-25, Terra Draw unless draw breaks on v6, skills/MCP install.
