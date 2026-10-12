# map-ux-hand-public

UX-12 remainder: anonymous `/mapa` may discover HAND rasters.

## In

- [ ] Add `hand` to `PUBLIC_PRODUCTION_LAYER_TYPES`
- [ ] Update `test_geo_public_layers.py` allowlist + tipo=hand filter

## Out

- New tile pipeline, Martin, admin `Capa.es_publica`
- Frontend toggle (dropdown already lists catalog HAND when `/geo/layers` returns it)
