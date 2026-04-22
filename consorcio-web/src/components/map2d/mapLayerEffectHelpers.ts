import type { FeatureCollection, LineString, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';

import { getMartinTileUrl } from '../../hooks/useMartinLayers';
import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import type { CanalFeatureProperties, Etapa } from '../../types/canales';
import type { EscuelaFeatureProperties } from '../../types/escuelas';
import {
  buildCanalesPropuestasFilter,
  buildCanalesPropuestasPaint,
  buildCanalesRelevadosFilter,
  buildCanalesRelevadosPaint,
} from './canalesLayers';
import { ESCUELAS_LAYER_ID, buildEscuelasCirclePaint } from './escuelasLayers';
import { SOURCE_IDS, buildWaterwayLayerConfigs } from './map2dConfig';
import { asFeatureCollection, ensureGeoJsonSource, setLayerVisibility } from './map2dUtils';
import {
  PILAR_VERDE_Z_ORDER,
  buildAgroAceptadaFillPaint,
  buildAgroAceptadaLinePaint,
  buildAgroPresentadaFillPaint,
  buildAgroPresentadaLinePaint,
  buildAgroZonasFillPaint,
  buildAgroZonasLinePaint,
  buildBpaHistoricoFillPaint,
  buildBpaHistoricoLinePaint,
  buildPorcentajeForestacionFillPaint,
} from './pilarVerdeLayers';
import {
  YPF_ESTACION_BOMBEO_GEOJSON,
  YPF_ESTACION_BOMBEO_LAYER_ID,
  YPF_ESTACION_BOMBEO_SOURCE_ID,
  buildYpfEstacionBombeoPaint,
} from './ypfEstacionBombeoLayer';

export function syncBaseTileVisibility(map: maplibregl.Map, baseLayer: 'osm' | 'satellite') {
  setLayerVisibility(map, 'osm-tiles', baseLayer === 'osm');
  setLayerVisibility(map, 'satellite-tiles', baseLayer === 'satellite');
}

export function syncWaterwayLayers(
  map: maplibregl.Map,
  waterwaysDefs: readonly (typeof WATERWAY_DEFS)[number][],
  isVisible: boolean
) {
  const waterwayFiles = buildWaterwayLayerConfigs(waterwaysDefs);

  for (const waterwayFile of waterwayFiles) {
    if (!map.getSource(waterwayFile.id)) {
      map.addSource(waterwayFile.id, { type: 'geojson', data: waterwayFile.url });
    }

    const lineLayerId = `${waterwayFile.id}-line`;
    if (!map.getLayer(lineLayerId)) {
      map.addLayer({
        id: lineLayerId,
        type: 'line',
        source: waterwayFile.id,
        paint: {
          'line-color': waterwayFile.color,
          'line-width': 3,
          'line-opacity': 0.9,
        },
      });
    }

    setLayerVisibility(map, lineLayerId, isVisible);
  }
}

export function syncSoilLayers(
  map: maplibregl.Map,
  soilCollection: FeatureCollection | null,
  isVisible: boolean
) {
  ensureGeoJsonSource(map, SOURCE_IDS.SOIL, soilCollection ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.SOIL}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SOIL}-fill`,
      type: 'fill',
      source: SOURCE_IDS.SOIL,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#8d6e63'],
        'fill-opacity': 0.3,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.SOIL}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SOIL}-line`,
      type: 'line',
      source: SOURCE_IDS.SOIL,
      paint: { 'line-color': '#6d4c41', 'line-width': 1.2, 'line-opacity': 0.85 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.SOIL}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.SOIL}-line`, isVisible);
}

export function syncCatastroLayers(map: maplibregl.Map, isVisible: boolean) {
  if (!map.getSource(SOURCE_IDS.CATASTRO)) {
    map.addSource(SOURCE_IDS.CATASTRO, {
      type: 'vector',
      tiles: [getMartinTileUrl('parcelas_catastro')],
      minzoom: 8,
      maxzoom: 19,
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.CATASTRO}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.CATASTRO}-fill`,
      type: 'fill',
      source: SOURCE_IDS.CATASTRO,
      'source-layer': 'parcelas_catastro',
      paint: { 'fill-color': '#8d6e63', 'fill-opacity': 0.08 },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.CATASTRO}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.CATASTRO}-line`,
      type: 'line',
      source: SOURCE_IDS.CATASTRO,
      'source-layer': 'parcelas_catastro',
      paint: { 'line-color': '#FFFFFF', 'line-width': 1.5, 'line-opacity': 0.85 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.CATASTRO}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.CATASTRO}-line`, isVisible);
}

/** Find the first waterway *-line layer currently mounted on the map, if any. */
function findFirstWaterwayLayerId(map: maplibregl.Map): string | undefined {
  const style = map.getStyle();
  return style?.layers?.find(
    (layer) => layer.id.startsWith(`${SOURCE_IDS.WATERWAYS}-`) && layer.id.endsWith('-line')
  )?.id;
}

export function syncRoadLayers(
  map: maplibregl.Map,
  roadsCollection: FeatureCollection | null | undefined,
  isVisible: boolean
) {
  ensureGeoJsonSource(map, SOURCE_IDS.ROADS, roadsCollection ?? asFeatureCollection([]));

  const roadLayerId = `${SOURCE_IDS.ROADS}-line`;
  if (!map.getLayer(roadLayerId)) {
    map.addLayer({
      id: roadLayerId,
      type: 'line',
      source: SOURCE_IDS.ROADS,
      paint: {
        'line-color': ['coalesce', ['get', 'color'], '#FFEB3B'],
        'line-width': 2,
        'line-opacity': 0.9,
      },
    });
  }

  // Ensure roads are drawn UNDER any existing waterway lines so the
  // hidrografía layer visually overlaps the red vial layer.
  const firstWaterwayLayerId = findFirstWaterwayLayerId(map);
  if (firstWaterwayLayerId && map.getLayer(roadLayerId)) {
    try {
      map.moveLayer(roadLayerId, firstWaterwayLayerId);
    } catch {
      // moveLayer can throw if the target id no longer exists between calls;
      // safe to ignore — next sync pass will retry.
    }
  }

  setLayerVisibility(map, roadLayerId, isVisible && !!roadsCollection);
}

export function syncBasinLayers(
  map: maplibregl.Map,
  basins: FeatureCollection | null | undefined,
  isVisible: boolean
) {
  ensureGeoJsonSource(map, SOURCE_IDS.BASINS, basins ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.BASINS}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.BASINS}-fill`,
      type: 'fill',
      source: SOURCE_IDS.BASINS,
      paint: { 'fill-color': '#00897B', 'fill-opacity': 0.08 },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.BASINS}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.BASINS}-line`,
      type: 'line',
      source: SOURCE_IDS.BASINS,
      paint: { 'line-color': '#00897B', 'line-width': 1.5, 'line-opacity': 0.95 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.BASINS}-fill`, isVisible && !!basins);
  setLayerVisibility(map, `${SOURCE_IDS.BASINS}-line`, isVisible && !!basins);
}

export function syncZonaLayer(map: maplibregl.Map, zonaCollection: FeatureCollection | null) {
  ensureGeoJsonSource(map, SOURCE_IDS.ZONA, zonaCollection ?? asFeatureCollection([]));

  if (!map.getLayer(`${SOURCE_IDS.ZONA}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.ZONA}-line`,
      type: 'line',
      source: SOURCE_IDS.ZONA,
      paint: { 'line-color': '#FF0000', 'line-width': 3, 'line-opacity': 0.95 },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.ZONA}-line`, !!zonaCollection);
}

export function syncApprovedZoneLayers(
  map: maplibregl.Map,
  approvedZonesCollection: FeatureCollection | null | undefined,
  isVisible: boolean
) {
  ensureGeoJsonSource(
    map,
    SOURCE_IDS.APPROVED_ZONES,
    approvedZonesCollection ?? asFeatureCollection([])
  );

  if (!map.getLayer(`${SOURCE_IDS.APPROVED_ZONES}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.APPROVED_ZONES}-fill`,
      type: 'fill',
      source: SOURCE_IDS.APPROVED_ZONES,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'fill-opacity': 0.18,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.APPROVED_ZONES}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.APPROVED_ZONES}-line`,
      type: 'line',
      source: SOURCE_IDS.APPROVED_ZONES,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }

  setLayerVisibility(
    map,
    `${SOURCE_IDS.APPROVED_ZONES}-fill`,
    isVisible && !!approvedZonesCollection
  );
  setLayerVisibility(
    map,
    `${SOURCE_IDS.APPROVED_ZONES}-line`,
    isVisible && !!approvedZonesCollection
  );
}

export function shouldShowSuggestedZones(params: {
  showSuggestedZonesPanel: boolean;
  hasApprovedZones: boolean;
  suggestedZonesDisplay: FeatureCollection | null;
}) {
  return (
    params.showSuggestedZonesPanel && !params.hasApprovedZones && !!params.suggestedZonesDisplay
  );
}

export function syncSuggestedZoneLayers(
  map: maplibregl.Map,
  suggestedZonesDisplay: FeatureCollection | null,
  isVisible: boolean
) {
  ensureGeoJsonSource(
    map,
    SOURCE_IDS.SUGGESTED_ZONES,
    suggestedZonesDisplay ?? asFeatureCollection([])
  );

  if (!map.getLayer(`${SOURCE_IDS.SUGGESTED_ZONES}-fill`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SUGGESTED_ZONES}-fill`,
      type: 'fill',
      source: SOURCE_IDS.SUGGESTED_ZONES,
      paint: {
        'fill-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'fill-opacity': 0.15,
      },
    });
  }

  if (!map.getLayer(`${SOURCE_IDS.SUGGESTED_ZONES}-line`)) {
    map.addLayer({
      id: `${SOURCE_IDS.SUGGESTED_ZONES}-line`,
      type: 'line',
      source: SOURCE_IDS.SUGGESTED_ZONES,
      paint: {
        'line-color': ['coalesce', ['get', '__color'], '#1971c2'],
        'line-width': 2,
        'line-opacity': 0.9,
        'line-dasharray': [4, 4],
      },
    });
  }

  setLayerVisibility(map, `${SOURCE_IDS.SUGGESTED_ZONES}-fill`, isVisible);
  setLayerVisibility(map, `${SOURCE_IDS.SUGGESTED_ZONES}-line`, isVisible);
}

/* -------------------------------------------------------------------------- */
/*  Pilar Verde sync helpers (Phase 2)                                         */
/*  Each helper is idempotent: addSource/addLayer are guarded by getSource/    */
/*  getLayer checks. After mount, layers are hoisted to match                  */
/*  `PILAR_VERDE_Z_ORDER` — iterating that tuple in order with                 */
/*  `map.moveLayer(id)` (no beforeId) raises each to the top, producing the    */
/*  documented stacking: zonas < forestación < presentada < aceptada < bpa.    */
/* -------------------------------------------------------------------------- */

/** Raise the mounted Pilar Verde fill+line layers to the top of the style
 * in the canonical z-order. Called at the tail of every Pilar Verde sync so
 * that re-renders keep the stack consistent even if other helpers ran in
 * between. Safe no-op when a layer is not yet mounted (catches the possible
 * race during first-mount). */
function raisePilarVerdeStack(map: maplibregl.Map) {
  for (const id of PILAR_VERDE_Z_ORDER) {
    const fillId = `${id}-fill`;
    const lineId = `${id}-line`;
    if (map.getLayer(fillId)) {
      try {
        map.moveLayer(fillId);
      } catch {
        // moveLayer can throw during concurrent style edits — ignore, next
        // sync pass will retry. The z-order constant is the single source
        // of truth for the intended stacking.
      }
    }
    if (map.getLayer(lineId)) {
      try {
        map.moveLayer(lineId);
      } catch {
        // see above
      }
    }
  }
}

/**
 * Sync the unified historical BPA layer (Phase 7).
 *
 * Replaces the old single-year `syncBpaLayer`. Source data comes from
 * `bpa_historico.geojson` (one feature per parcel with `años_bpa >= 1`);
 * fill uses a gradient expression on `años_bpa` so the user can read
 * commitment depth at a glance.
 */
export function syncBpaHistoricoLayer(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  isVisible: boolean
) {
  const id = SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO;
  ensureGeoJsonSource(map, id, collection ?? asFeatureCollection([]));

  if (!map.getLayer(`${id}-fill`)) {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      paint: buildBpaHistoricoFillPaint(),
    });
  }

  if (!map.getLayer(`${id}-line`)) {
    map.addLayer({
      id: `${id}-line`,
      type: 'line',
      source: id,
      paint: buildBpaHistoricoLinePaint(),
    });
  }

  setLayerVisibility(map, `${id}-fill`, isVisible);
  setLayerVisibility(map, `${id}-line`, isVisible);

  // BPA historical is topmost → hoist the full Pilar Verde stack in z-order.
  raisePilarVerdeStack(map);
}

export function syncAgroAceptadaLayer(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  isVisible: boolean
) {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA;
  ensureGeoJsonSource(map, id, collection ?? asFeatureCollection([]));

  if (!map.getLayer(`${id}-fill`)) {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      paint: buildAgroAceptadaFillPaint(),
    });
  }

  if (!map.getLayer(`${id}-line`)) {
    map.addLayer({
      id: `${id}-line`,
      type: 'line',
      source: id,
      paint: buildAgroAceptadaLinePaint(),
    });
  }

  setLayerVisibility(map, `${id}-fill`, isVisible);
  setLayerVisibility(map, `${id}-line`, isVisible);
  raisePilarVerdeStack(map);
}

export function syncAgroPresentadaLayer(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  isVisible: boolean
) {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA;
  ensureGeoJsonSource(map, id, collection ?? asFeatureCollection([]));

  if (!map.getLayer(`${id}-fill`)) {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      paint: buildAgroPresentadaFillPaint(),
    });
  }

  if (!map.getLayer(`${id}-line`)) {
    map.addLayer({
      id: `${id}-line`,
      type: 'line',
      source: id,
      paint: buildAgroPresentadaLinePaint(),
    });
  }

  setLayerVisibility(map, `${id}-fill`, isVisible);
  setLayerVisibility(map, `${id}-line`, isVisible);
  raisePilarVerdeStack(map);
}

export function syncAgroZonasLayer(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  isVisible: boolean
) {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_ZONAS;
  ensureGeoJsonSource(map, id, collection ?? asFeatureCollection([]));

  if (!map.getLayer(`${id}-fill`)) {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      paint: buildAgroZonasFillPaint(),
    });
  }

  if (!map.getLayer(`${id}-line`)) {
    map.addLayer({
      id: `${id}-line`,
      type: 'line',
      source: id,
      paint: buildAgroZonasLinePaint(),
    });
  }

  setLayerVisibility(map, `${id}-fill`, isVisible);
  setLayerVisibility(map, `${id}-line`, isVisible);
  raisePilarVerdeStack(map);
}

export function syncPorcentajeForestacionLayer(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  isVisible: boolean
) {
  const id = SOURCE_IDS.PILAR_VERDE_PORCENTAJE_FORESTACION;
  ensureGeoJsonSource(map, id, collection ?? asFeatureCollection([]));

  // No line layer — this is a low-contrast background context fill only.
  if (!map.getLayer(`${id}-fill`)) {
    map.addLayer({
      id: `${id}-fill`,
      type: 'fill',
      source: id,
      paint: buildPorcentajeForestacionFillPaint(),
    });
  }

  setLayerVisibility(map, `${id}-fill`, isVisible);
  raisePilarVerdeStack(map);
}

/* -------------------------------------------------------------------------- */
/*  Pilar Azul (Canales) sync helper                                          */
/*                                                                            */
/*  ONE helper for both relevados + propuestos — they share infra (same data  */
/*  shape, same mount/filter pattern) and rendering both in a single pass     */
/*  keeps `raiseCanalesStack` consistent across visibility flips.             */
/*                                                                            */
/*  The helper is idempotent: addSource/addLayer are guarded by               */
/*  getSource/getLayer checks. `setFilter` + `setLayerVisibility` are the     */
/*  "hot path" called on every re-render.                                     */
/* -------------------------------------------------------------------------- */

export interface SyncCanalesLayersParams {
  /** Relevados FeatureCollection — `null` renders an empty source. */
  relevados: FeatureCollection<LineString, CanalFeatureProperties> | null;
  /** Propuestos FeatureCollection — `null` renders an empty source. */
  propuestas: FeatureCollection<LineString, CanalFeatureProperties> | null;
  /** Master toggle state for the relevados layer. */
  relevadosVisible: boolean;
  /** Master toggle state for the propuestos layer. */
  propuestasVisible: boolean;
  /** Slugs currently visible in the relevados layer (after per-canal filter). */
  visibleRelevadoIds: readonly string[];
  /** Slugs currently visible in the propuestos layer (after per-canal + etapa filter). */
  visiblePropuestaIds: readonly string[];
  /**
   * Etapas currently visible — used by the propuestos layer filter's second
   * branch. Pass ALL 5 when the user hasn't filtered anything; pass the
   * subset when they've toggled some off.
   */
  activeEtapas: readonly Etapa[];
}

/**
 * Raise the canales stack to the top AFTER each sync pass so pilar-verde
 * fills (if mounted) still overlay them in click precedence — canales are
 * line features, fills "win" on pixel-overlap in MapLibre z-order.
 */
function raiseCanalesStack(map: maplibregl.Map) {
  const ids = [`${SOURCE_IDS.CANALES_RELEVADOS}-line`, `${SOURCE_IDS.CANALES_PROPUESTOS}-line`];
  for (const id of ids) {
    if (map.getLayer(id)) {
      try {
        map.moveLayer(id);
      } catch {
        // moveLayer can race with concurrent style edits — safe to ignore,
        // next pass will retry.
      }
    }
  }
}

export function syncCanalesLayers(map: maplibregl.Map, params: SyncCanalesLayersParams): void {
  const {
    relevados,
    propuestas,
    relevadosVisible,
    propuestasVisible,
    visibleRelevadoIds,
    visiblePropuestaIds,
    activeEtapas,
  } = params;

  const relevadosSrcId = SOURCE_IDS.CANALES_RELEVADOS;
  const propuestosSrcId = SOURCE_IDS.CANALES_PROPUESTOS;
  const relevadosLayerId = `${relevadosSrcId}-line`;
  const propuestosLayerId = `${propuestosSrcId}-line`;

  // ── Sources (idempotent) ──
  ensureGeoJsonSource(
    map,
    relevadosSrcId,
    (relevados ?? asFeatureCollection([])) as FeatureCollection
  );
  ensureGeoJsonSource(
    map,
    propuestosSrcId,
    (propuestas ?? asFeatureCollection([])) as FeatureCollection
  );

  // ── Layers (idempotent) ──
  if (!map.getLayer(relevadosLayerId)) {
    map.addLayer({
      id: relevadosLayerId,
      type: 'line',
      source: relevadosSrcId,
      paint: buildCanalesRelevadosPaint(),
    });
  }
  if (!map.getLayer(propuestosLayerId)) {
    map.addLayer({
      id: propuestosLayerId,
      type: 'line',
      source: propuestosSrcId,
      paint: buildCanalesPropuestasPaint(),
    });
  }

  // ── Filters (hot path — called on every render) ──
  map.setFilter(relevadosLayerId, buildCanalesRelevadosFilter(visibleRelevadoIds));
  map.setFilter(propuestosLayerId, buildCanalesPropuestasFilter(visiblePropuestaIds, activeEtapas));

  // ── Visibility (master toggles) ──
  setLayerVisibility(map, relevadosLayerId, relevadosVisible);
  setLayerVisibility(map, propuestosLayerId, propuestasVisible);

  // ── Z-order ──
  raiseCanalesStack(map);
}

/* -------------------------------------------------------------------------- */
/*  Pilar Azul (Escuelas rurales) sync helper                                 */
/*                                                                            */
/*  ONE MapLibre-native layer backed by a single geojson source:              */
/*    - `escuelas-symbol` (type: 'circle') — the clickable point. Its id      */
/*      keeps the historical `-symbol` suffix so the click-precedence test    */
/*      (pinned at index 10 in `buildClickableLayers`) and the InfoPanel      */
/*      discriminator branch do not need to change.                           */
/*                                                                            */
/*  History: a companion text-only `symbol` label layer rendered the          */
/*  `nombre` property beneath each circle. It was removed because any         */
/*  MapLibre `symbol` layer using `text-field` requires a `glyphs` URL on     */
/*  the style, and this deployment does NOT configure a glyphs endpoint.      */
/*  The feature name is shown on click via `EscuelaCard` inside `InfoPanel`   */
/*  — that is the designed UX.                                                */
/*                                                                            */
/*  Motivation for the circle: the previous symbol+icon-image approach had    */
/*  two successive silent-fail paths (MapLibre v4 Promise loadImage API +     */
/*  generic symbol-layer-hides-when-icon-missing behavior). For seven static  */
/*  points the asset pipeline buys nothing — the native circle layer is       */
/*  synchronous, deterministic, and has no silent-fail modes.                 */
/*                                                                            */
/*  Null-tolerance contract: when `useEscuelas()` graceful-degrades to        */
/*  `collection: null` (fetch failure), we still mount an empty              */
/*  FeatureCollection on the source so `setLayerVisibility` has something to  */
/*  act on — same pattern as `syncSoilLayers`.                                */
/*                                                                            */
/*  Toggle OFF uses visibility-none (NOT removeLayer/removeSource) — matches  */
/*  the Pilar Verde / canales / soil patterns. This preserves the source +   */
/*  layer mount across toggle cycles.                                         */
/* -------------------------------------------------------------------------- */

export function syncEscuelasLayer(
  map: maplibregl.Map,
  collection: FeatureCollection<Point, EscuelaFeatureProperties> | null,
  isVisible: boolean
): void {
  const sourceId = SOURCE_IDS.ESCUELAS;
  const circleLayerId = ESCUELAS_LAYER_ID;

  // ── Source (idempotent) ──
  // Cast-erase the point-feature narrowing for `ensureGeoJsonSource` which
  // accepts the broader `FeatureCollection`. The runtime shape is identical.
  ensureGeoJsonSource(map, sourceId, (collection ?? asFeatureCollection([])) as FeatureCollection);

  // ── Circle layer (idempotent) ──
  if (!map.getLayer(circleLayerId)) {
    map.addLayer({
      id: circleLayerId,
      type: 'circle',
      source: sourceId,
      paint: buildEscuelasCirclePaint(),
    });
  }

  // ── Visibility (master toggle) ──
  setLayerVisibility(map, circleLayerId, isVisible);
}

/* -------------------------------------------------------------------------- */
/*  YPF estación de bombeo — single hardcoded landmark                        */
/*                                                                            */
/*  Sibling of `syncEscuelasLayer` but radically simpler:                     */
/*    - ONE MapLibre-native `circle` layer backed by the hardcoded            */
/*      FeatureCollection from `ypfEstacionBombeoLayer.ts`.                   */
/*    - NO visibility flag — the layer is always mounted AND always visible   */
/*      from map init (no tear-down path).                                    */
/*    - Idempotent: addSource/addLayer are guarded by getSource/getLayer so   */
/*      re-running the effect is safe.                                        */
/* -------------------------------------------------------------------------- */

export function syncYpfEstacionBombeoLayer(map: maplibregl.Map): void {
  // ── Source (idempotent) ──
  ensureGeoJsonSource(
    map,
    YPF_ESTACION_BOMBEO_SOURCE_ID,
    YPF_ESTACION_BOMBEO_GEOJSON as unknown as FeatureCollection
  );

  // ── Circle layer (idempotent) ──
  if (!map.getLayer(YPF_ESTACION_BOMBEO_LAYER_ID)) {
    map.addLayer({
      id: YPF_ESTACION_BOMBEO_LAYER_ID,
      type: 'circle',
      source: YPF_ESTACION_BOMBEO_SOURCE_ID,
      paint: buildYpfEstacionBombeoPaint(),
    });
  }

  // No visibility toggle — the layer is always-on by design.
}
