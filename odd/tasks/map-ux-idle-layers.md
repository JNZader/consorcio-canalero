# map-ux-idle-layers

Defer `/mapa` caminos + waterways fetches until `requestIdleCallback` (existing `useDeferredIdleMount`).

## Lighthouse (measured 2026-10-12, this laptop)

URL `https://consorcio-canalero.pages.dev/mapa`, Lighthouse **12.8.2**, mobile 412×823.

| | Audit v5 (11/10 ~13:50 BA) | This run |
|---|---|---|
| Perf | 49 | **38** |
| TBT | 7660 ms | **6357 ms** |
| TTI | 19.2 s | **21.5 s** |
| LCP | — | 4684 ms |

Not the same lab. Do not treat PERF-01 as closed. Idle fetch is the remaining TBT bet without splitting `MapaMapLibre`.

## In

- [ ] `useCaminosColoreados({ enabled })` / `useWaterways({ enabled })` default true
- [ ] `MapaMapLibre` gates those two on `useDeferredIdleMount()`
- [ ] Tests: `enabled: false` does not fetch

## Out

- Landing / form / 3D hooks
- Splitting `MapaMapLibre`
- Claiming a new Lighthouse score without a post-merge re-run
