# Review Ledger — `review-reliability`

## Change

`rainfall-analysis-cache-freshness` (Approach B + Option A)

## Branch

`verify/lluvia-rainfall-e2e`

## Lens

reliability

---

## Findings

| id | lens | location | severity | status | evidence |
|---|---|---|---|---|---|
| R3-001 | reliability | `consorcio-web/src/styles/components/map.module.css:241-267` | CRITICAL | verified | Refactored desktop card layout: removed `overflow-y: auto` from `.infoPanel` / `.fichaPanel` and added `.panelCardBody` as the scrollable inner wrapper with `overflow-y: auto` and `pointer-events: auto`. The native scrollbar now lives on a container that has pointer events enabled, so the scrollbar thumb/track are clickable/draggable. Re-verified by the E2E multi-parcel journey (11/0/0/0) and 212/212 unit tests. |
| R3-002 | reliability | `consorcio-web/src/styles/components/map.module.css:312-314` | CRITICAL | verified | Removed the broad `.fichaPanel svg { pointer-events: none; }` rule entirely. The SVG now inherits `pointer-events: auto` from the `.panelCardBody` wrapper, so Recharts `<Tooltip>` receives mouse/pointer events. Re-verified by the E2E multi-parcel journey (11/0/0/0) and 212/212 unit tests. |
| R3-003 | reliability | `consorcio-web/tests/unit/RainfallDetailPanel.test.tsx:1349` | WARNING | info | The 100 ms fixed-duration race in the same-`nomenclatura` cache-reuse test is acknowledged. It is not addressed in this fix round because it is a test-only determinism issue and does not affect the production cache-freshness contract. Consider replacing with `waitFor` polling in a follow-up. |
| R3-004 | reliability | `consorcio-web/src/styles/components/map.module.css:269-306` | SUGGESTION | info | The long interactive-element allowlist is now obsolete: the refactor wraps all card content in `.panelCardBody` with `pointer-events: auto`, so interactive descendants work without an allowlist. The suggestion's underlying concern (future interactive children becoming unreachable) is resolved by the wrapper design. |

## Notes

- `isRepeatSelection` correctly identifies any alias that already appears earlier in the journey. For the current `A→B→C→A` fixture this exactly matches the final `C→A` gate, and the strict trace/sequence checks are preserved for first-time transitions (`A→B`, `B→C`). This is working as intended for Option A.
- `dismissDesktopPanel` is deterministic: it returns early when the close button is absent (already closed/minimized), clicks the close button when present, and polls until either the pill is visible or the panel unmounts. No extra handling is needed for the InfoPanel because the CSS guard already lets map clicks pass through both panels.
- The per-parcel query-key change in `useRainfallAnalysis` and the removal of `invalidateQueries` from `RainfallDetailPanel` are behaviorally correct and match the spec.
- Existing panel-related unit tests (`MapPanelMinimizePill`, `MapUiPanelsLayout`, `mapPanelFadeClearance`) assert on classes, DOM presence, and fade geometry, not on pointer-events or scrollbar behavior, so the CSS regressions above are not covered by them.
