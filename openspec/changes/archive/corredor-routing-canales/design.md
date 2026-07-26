# Design: Corridor routing para trazado de canales

## Technical Approach

La feature quedó en dos modos complementarios:

1. **`network`**: usa la red pgRouting existente, perfiles sobre edges y alternativas penalizadas
2. **`raster`**: usa least-cost path raster real con superficie multi-criterio

Ambos comparten el mismo contrato general de respuesta: `centerline`, `corridor`, `alternatives`, `summary`.

## Architecture Decisions

### Decision: Reuse the existing network routing stack
**Choice**: implementar el MVP sobre `canal_network` + `pgr_dijkstra`.

**Rationale**: ya existe infraestructura, tests y contratos parciales. Esto permite entregar valor rápido sin bloquearse en el costo raster.

### Decision: Build corridor geometry in Python
**Choice**: usar Shapely para unir LineStrings y construir el buffer del corredor.

**Rationale**: evita complejidad SQL innecesaria en el MVP y facilita tests unitarios puros.

### Decision: Penalized alternatives
**Choice**: generar alternativas con una variante de shortest path que aplique un multiplicador de costo a edges ya usados.

**Rationale**: simple, explicable y suficiente para una primera versión.

### Decision: Named profile presets over ad-hoc tuning
**Choice**: introducir perfiles `balanceado`, `hidraulico` y `evitar_propiedad` que resuelvan defaults de ancho, alternativas y penalización, dejando overrides explícitos opcionales.

**Rationale**: permite una UX simple en frontend/admin sin bloquear futuras extensiones multi-criterio ni quitar control fino cuando haga falta.

### Decision: Add real raster mode without breaking the network contract
**Choice**: agregar `mode = raster` reutilizando `generate_cost_surface`, `cost_distance` y `least_cost_path`, pero devolviendo la misma forma de respuesta principal.

**Rationale**: permite evolucionar a routing multi-criterio real sin romper frontend ni escenarios guardados.

### Decision: Persist approval state in the scenario table
**Choice**: ampliar `geo_routing_scenarios` con `is_approved`, `approved_at` y `approved_by_id`.

**Rationale**: approval es parte del ciclo de vida del escenario, no un recurso aparte.

## Proposed Backend Changes

### `routing.py`
Agregar helpers puros y de acceso:

- `shortest_path_with_penalties(...)`
- `build_route_feature_collection(...)`
- `build_corridor_polygon(...)`
- `build_corridor_response(...)`
- `compute_route_alternatives(...)`
- `corridor_routing(...)`
- `resolve_routing_profile(...)`

### `router_hydrology_routing.py`
Agregar:

- `CorridorRoutingRequest`
- endpoint `POST /routing/corridor`
- campo `profile` en el request
- endpoints para guardar/listar/exportar escenarios persistidos
- endpoint para aprobar escenario
- endpoint para exportar escenario a PDF

### `router.py`
Re-exportar el endpoint si hace falta para mantener patrones de test/import existentes.

### Persistencia de escenarios
Se agrega una tabla dedicada `geo_routing_scenarios` para no forzar `AnalisisGeo` ni ampliar enums existentes. Guarda:

- `name`
- `profile`
- `request_payload`
- `result_payload`
- `notes`
- `created_by_id`
- `is_approved`
- `approved_at`
- `approved_by_id`

### Modo raster multi-criterio
Se agrega `routing_raster_support.py` para:

- resolver el raster de pendiente más reciente
- construir una superficie de costo multi-criterio
- rasterizar restricciones/penalizaciones de propiedad
- rasterizar preferencia hidrológica por zona
- trazar least-cost path y convertirlo a GeoJSON WGS84

## Data Flow

```text
coords -> nearest vertices -> shortest_path
                         -> alternatives with penalties
path edges -> FeatureCollection (centerline)
path edges -> merged lines -> buffer(width_m) -> corridor polygon
```

## Response Shape

```json
{
  "source": {...},
  "target": {...},
  "summary": {
    "profile": "balanceado",
    "total_distance_m": 1234.5,
    "edges": 8,
    "corridor_width_m": 50,
    "penalty_factor": 3.0
  },
  "centerline": { "type": "FeatureCollection", "features": [...] },
  "corridor": { "type": "Feature", "geometry": {...}, "properties": {...} },
  "alternatives": [
    {
      "rank": 1,
      "edge_ids": [1,2,3],
      "total_distance_m": 1400.0,
      "edges": 9,
      "geojson": { "type": "FeatureCollection", "features": [...] }
    }
  ]
}
```

## TDD Strategy

### Unit tests first
- corridor polygon from route edges
- alternative ordering and summaries
- empty-route handling
- endpoint contract with mocks

### Then implementation
- helpers puros
- orchestrator en `routing.py`
- endpoint/router

## Future Extension Path

La evolución futura puede agregar:
- alternativas raster reales
- PDF con mapa embebido
- aprobación con workflow más formal
- wide corridor / cost-distance surfaces más ricas
