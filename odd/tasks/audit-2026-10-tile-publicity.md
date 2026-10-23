# audit-2026-10-tile-publicity

Fixes audit finding C1/GEO-1 from
`docs/auditorias/AUDITORIA_CONSORCIO_CANALERO_2026-10-23.md`: the public tile
proxy (`GET /api/v2/geo/layers/{layer_id}/tiles/{z}/{x}/{y}.png`) ran its only
publicity check inside the rescale branch, so the default request shape (no
rescale params) forwarded ANY `GeoLayer` UUID to the geo-worker — whose
`get_tile` selects by id with no tipo/publicity filter — giving anonymous,
rate-limit-exempt access to the 8 private DEM layer types and manual sources.

## In

- [x] Publicity gate hoisted in `router_core.proxy_tile`: runs UNCONDITIONALLY
      before forwarding. Order is now rescale globals → publicity gate →
      pyramid 204 fast path → forward.
- [x] Fail closed: `SQLAlchemyError` on the gate lookup → 503, no forward
      (comment states the pre-existing degrade-on-error block applied to the
      rescale OVERRIDE decision, not to authorization, and is retired because
      the single lookup now serves both roles).
- [x] Non-public layer → 404 ALWAYS (previously only when rescale params were
      present); 404 over 403 so anonymous callers cannot confirm private ids.
- [x] Lookup/warn-throttle helpers renamed to their new role
      (`_public_layer_for_tile`, `_publicity_lookup_warn_*`); throttle logic
      unchanged.
- [x] Regression tests in `tests/new/test_geo_public_route_caps.py`:
      private tipo + NO rescale → 404 (red-checked against the unfixed code:
      the request was really forwarded to geo-worker, `assert 204 == 404`
      failed); public layer + no rescale → forwarded 200; publicity lookup DB
      failure → 503 with no forward.
- [x] `tests/new/test_proxy_tile_rescale_db_failure.py` rewritten to pin the
      fail-closed contract (it pinned the old degrade-forward behavior this
      fix deliberately removes); warning/throttle/recovery/programmer-error
      assertions preserved.
- [x] Two existing pyramid tests now seed a public layer (the gate runs before
      the 204 fast path, so a random id would 404 first).

## Out

- No changes to the geo-worker `tile_service.py` (`get_tile` still selects by
  id with no publicity filter — it trusts the network; defense stays at the
  proxy, the only public entry point).
- No per-tile auth or rate limiting added (route stays public and exempt by
  design; the gate is the authorization boundary).
- No cache purge / CDN invalidation for tiles of private layers that may have
  been fetched with `Cache-Control: public` before this fix (deployment
  concern, flagged to the coordinator).
