/**
 * informeAreaLayers.ts — everything the informe de área touches on the MAP:
 * the click bridge, the highlight source/layers and the selection outline.
 *
 * WHY A DEDICATED SOURCE (S7 investigation, answer (a)): the map's BASINS
 * layer is a GeoJSON source fed from the public `/geo/basins` endpoint (NOT
 * the Martin `vt_zonas_operativas` vector view — that view is not rendered by
 * the 2D map), and its features DO carry the stable `zonas_operativas` uuid as
 * `properties.id`. But the shared source is registered via
 * `ensureGeoJsonSource` WITHOUT `promoteId`, so its features have no MapLibre
 * feature id and `setFeatureState({selected: true})` cannot address them. This
 * module registers its own source over the SAME data with
 * `promoteId: 'id'` — the existing basins layer is left untouched.
 *
 * WHY A CLICK BRIDGE instead of a new `MapInteractionMode`: the mode union and
 * its coordinator (`useFichaInteraction` → `useMapaMapLibreStage`) live outside
 * this change's edit surface. `useMapInteractionEffects` (which owns every map
 * click) registers itself as the bridge's map provider and, while the Elegir
 * step is active, routes clicks here BEFORE the idle parcel path — the same
 * exclusivity `ficha-canal` mode has. One map exists per page, so a
 * module-level bridge is a singleton by construction.
 */

import type {
  Feature,
  FeatureCollection,
  Geometry,
  MultiPolygon,
  Polygon,
  Position,
} from 'geojson';
import type * as maplibregl from 'maplibre-gl';
import { useEffect, useState } from 'react';

import { mapColorTokens } from '../../../lib/theme';

/** A subcuenca resolved from a map click — `/geo/basins` feature properties. */
export interface ZonaResuelta {
  readonly id: string;
  readonly nombre: string;
  readonly cuenca: string;
}

// ── click bridge ─────────────────────────────────────────────────────────────

interface InformeAreaBridge {
  /** Installed by `useMapInteractionEffects` while its map is live. */
  getMap: (() => maplibregl.Map | null) | null;
  /**
   * Mode-transition hook installed by the interaction effects: entering the
   * informe de área discards the previous selection (design §6.5), exactly like
   * every other ficha mode transition.
   */
  enter: (() => void) | null;
  /** True while the Elegir step owns map clicks. */
  activo: boolean;
  /** The drawer's click consumer; `null` while inactive. */
  onZonaPicked: ((zona: ZonaResuelta, additive: boolean) => void) | null;
  /** Notified whenever `getMap` is (un)registered — the drawer waits on it. */
  listeners: Set<() => void>;
}

const bridge: InformeAreaBridge = {
  getMap: null,
  enter: null,
  activo: false,
  onZonaPicked: null,
  listeners: new Set(),
};

/**
 * Register the map provider + the mode-transition hook. Called by
 * `useMapInteractionEffects` for the lifetime of its effect; the returned
 * unregister keeps a late unmount from dangling the pointer.
 */
export function registrarPuenteInformeArea(params: {
  getMap: () => maplibregl.Map | null;
  enter: () => void;
}): () => void {
  bridge.getMap = params.getMap;
  bridge.enter = params.enter;
  for (const listener of bridge.listeners) listener();
  return () => {
    if (bridge.getMap === params.getMap) {
      bridge.getMap = null;
      bridge.enter = null;
      for (const listener of bridge.listeners) listener();
    }
  };
}

/**
 * Activate informe-area click ownership (the Elegir step). Fires the
 * mode-transition `enter` once so the previous ficha selection is discarded —
 * UNLESS `descartarSeleccionPrevia` is `false` (see the drawer: the wired
 * `enter` resolves `parcela=null`, whose plain-click branch resets the ENTIRE
 * ficha state to IDLE, which deactivates the host panel and unmounts this very
 * drawer the instant it opens. Runtime evidence: the T4 e2e). Returns the
 * deactivation function.
 */
export function activarSeleccionDeZonas(
  onZonaPicked: (zona: ZonaResuelta, additive: boolean) => void,
  { descartarSeleccionPrevia = true }: { descartarSeleccionPrevia?: boolean } = {}
): () => void {
  bridge.activo = true;
  bridge.onZonaPicked = onZonaPicked;
  if (descartarSeleccionPrevia) bridge.enter?.();
  return () => {
    bridge.activo = false;
    bridge.onZonaPicked = null;
  };
}

/** True while the informe de área owns map clicks (read at event time). */
export function puenteInformeAreaActivo(): boolean {
  return bridge.activo;
}

/**
 * Deliver a resolved zona + the additive gesture to the drawer's handler, if
 * one is active. Called by `useMapInteractionEffects` — the only click owner.
 */
export function informeAreaPicked(zona: ZonaResuelta, additive: boolean): void {
  bridge.onZonaPicked?.(zona, additive);
}

/**
 * Resolve the informeArea layer features under a click into a zona. Exported
 * for the interaction-effects wiring; reads `properties.id` (present on every
 * `/geo/basins` feature) rather than the promoted feature id, because
 * `queryRenderedFeatures` output shape for promoted ids is easy to get wrong
 * and the property is the authoritative wire value.
 */
export function resolverZona(features: readonly Feature[]): ZonaResuelta | null {
  for (const feature of features) {
    const props = (feature.properties ?? {}) as Record<string, unknown>;
    const id = typeof props.id === 'string' ? props.id.trim() : '';
    if (!id) continue;
    return {
      id,
      nombre: typeof props.nombre === 'string' && props.nombre.trim() ? props.nombre.trim() : id,
      cuenca: typeof props.cuenca === 'string' ? props.cuenca.trim() : '',
    };
  }
  return null;
}

/**
 * React access to the map instance: resolves the bridge's provider and
 * re-renders when it is (un)registered. The drawer cannot receive `mapRef` as
 * a prop (its entry point lives in `FichaTerritorialPanel`, which the
 * container does not thread a map through), so this is the one sanctioned
 * path to the map from inside the informeArea module.
 */
export function useInformeAreaMap(): maplibregl.Map | null {
  const [map, setMap] = useState<maplibregl.Map | null>(() => bridge.getMap?.() ?? null);
  useEffect(() => {
    const reavisar = () => setMap(bridge.getMap?.() ?? null);
    reavisar();
    bridge.listeners.add(reavisar);
    return () => {
      bridge.listeners.delete(reavisar);
    };
  }, []);
  return map;
}

// ── highlight source + layers ────────────────────────────────────────────────

export const INFORME_AREA_SOURCE = 'informe-area-basins';
export const INFORME_AREA_FILL_LAYER = `${INFORME_AREA_SOURCE}-fill`;
export const INFORME_AREA_LINE_LAYER = `${INFORME_AREA_SOURCE}-line`;
export const INFORME_AREA_OUTLINE_SOURCE = 'informe-area-seleccion';
export const INFORME_AREA_OUTLINE_LAYER = `${INFORME_AREA_OUTLINE_SOURCE}-line`;

/** Selected-state fill opacity for the feature-state expression. */
const OPACIDAD_SELECCIONADA = 0.4;
/** Resting opacity — mirrors the shared basins fill so the layer reads as context. */
const OPACIDAD_CONTEXTO = 0.08;

/**
 * Ensure the informeArea source (with `promoteId: 'id'`, the whole point of
 * this source — see the module doc) and its fill/line layers exist on the map.
 * Safe to call repeatedly; a `null` collection installs an empty source so the
 * layers exist before the data lands.
 */
export function sincronizarFuenteZonas(
  map: maplibregl.Map,
  collection: FeatureCollection | null
): void {
  const data = collection ?? { type: 'FeatureCollection', features: [] };
  const source = map.getSource(INFORME_AREA_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  } else {
    map.addSource(INFORME_AREA_SOURCE, {
      type: 'geojson',
      data,
      // The one thing the shared BASINS source lacks: a stable feature id.
      promoteId: 'id',
    });
  }

  if (!map.getLayer(INFORME_AREA_FILL_LAYER)) {
    map.addLayer({
      id: INFORME_AREA_FILL_LAYER,
      type: 'fill',
      source: INFORME_AREA_SOURCE,
      paint: {
        'fill-color': mapColorTokens.h00897B,
        'fill-opacity': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          OPACIDAD_SELECCIONADA,
          OPACIDAD_CONTEXTO,
        ],
      },
    });
  }

  if (!map.getLayer(INFORME_AREA_LINE_LAYER)) {
    map.addLayer({
      id: INFORME_AREA_LINE_LAYER,
      type: 'line',
      source: INFORME_AREA_SOURCE,
      // Only the SELECTED zonas get an outline: the shared basins layer
      // already draws every boundary, a second full outline is noise. The
      // "selected only" rule lives in PAINT, NOT in `filter`: the MapLibre
      // style spec rejects `feature-state` expressions inside filters
      // ("feature-state data expressions are not supported with filters"),
      // and an addLayer that throws takes the whole map subtree down with
      // the app's error boundary.
      paint: {
        'line-color': mapColorTokens.h00897B,
        'line-width': 2,
        'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.95, 0],
      },
    });
  }
}

/**
 * Push the selection into feature states (`setFeatureState({selected})` + the
 * fill-opacity expression above). Iterates the collection's features — not the
 * selection — so REMOVED zonas are cleared too.
 */
export function aplicarSeleccionEnMapa(
  map: maplibregl.Map,
  collection: FeatureCollection | null,
  seleccion: ReadonlySet<string>
): void {
  if (!map.getSource(INFORME_AREA_SOURCE) || !collection) return;
  for (const feature of collection.features) {
    const id = (feature.properties as Record<string, unknown> | null)?.id;
    if (typeof id !== 'string' || !id) continue;
    map.setFeatureState({ source: INFORME_AREA_SOURCE, id }, { selected: seleccion.has(id) });
  }
}

/** Remove every layer/source this module added, and drop feature states. */
export function limpiarCapasInformeArea(
  map: maplibregl.Map,
  collection: FeatureCollection | null
): void {
  for (const layerId of [
    INFORME_AREA_FILL_LAYER,
    INFORME_AREA_LINE_LAYER,
    INFORME_AREA_OUTLINE_LAYER,
  ]) {
    if (map.getLayer(layerId)) map.removeLayer(layerId);
  }
  for (const sourceId of [INFORME_AREA_SOURCE, INFORME_AREA_OUTLINE_SOURCE]) {
    if (map.getSource(sourceId)) map.removeSource(sourceId);
  }
  // Feature states die with their source; the collection loop is only for
  // maps whose source was replaced by a later drawer open.
  if (collection) {
    for (const feature of collection.features) {
      const id = (feature.properties as Record<string, unknown> | null)?.id;
      if (typeof id === 'string' && id) {
        map.removeFeatureState({ source: INFORME_AREA_SOURCE, id });
      }
    }
  }
}

// ── selection outline + fitBounds ────────────────────────────────────────────

/** Every numeric coordinate of polygonal geometries, flattened once. */
function posicionesDe(geometrias: readonly Geometry[]): Position[] {
  const posiciones: Position[] = [];
  for (const geometria of geometrias) {
    if (geometria.type !== 'Polygon' && geometria.type !== 'MultiPolygon') continue;
    const anillos: readonly Position[][] =
      geometria.type === 'Polygon' ? geometria.coordinates : geometria.coordinates.flat();
    for (const anillo of anillos) posiciones.push(...anillo);
  }
  return posiciones.filter(
    (posicion) => typeof posicion[0] === 'number' && typeof posicion[1] === 'number'
  );
}

/** Deep bbox [west, south, east, north] over polygonal geometries. */
function bboxDeGeometrias(
  geometrias: readonly Geometry[]
): [number, number, number, number] | null {
  const posiciones = posicionesDe(geometrias);
  if (posiciones.length === 0) return null;
  const eje = (indice: 0 | 1): number[] => posiciones.map((posicion) => posicion[indice]);
  const lngs = eje(0);
  const lats = eje(1);
  return [
    lngs.reduce((a, b) => Math.min(a, b)),
    lats.reduce((a, b) => Math.min(a, b)),
    lngs.reduce((a, b) => Math.max(a, b)),
    lats.reduce((a, b) => Math.max(a, b)),
  ];
}

/**
 * Paint the outline of the current selection (the Revisar/Generar steps) and
 * `fitBounds` to it.
 *
 * DEVIATION from S5's "contorno unido": a true dissolve needs a polygon-union
 * library (`@turf/union` is NOT a dependency and PR 1 adds none), and the
 * preview response carries no geometry (geometry-only areas, by design). The
 * outline is therefore the PER-ZONA outlines of the selected subcuencas over
 * `/geo/basins` geometries — adjacent zonas tile their union, so the visual
 * result is the selected extent framed — plus the exact union bbox for
 * `fitBounds`.
 *
 * PR 3: `ajustar: false` paints the drawn/imported geometries of the
 * selection while the user is STILL CHOOSING (paso Elegir) — the same
 * source/layer, without moving the map under their feet.
 */
export function pintarContornoSeleccion(
  map: maplibregl.Map,
  geometrias: readonly Geometry[],
  { ajustar = true }: { ajustar?: boolean } = {}
): void {
  const features: Feature[] = geometrias.map((geometry, indice) => ({
    type: 'Feature',
    id: indice,
    properties: {},
    geometry,
  }));
  const data: FeatureCollection = { type: 'FeatureCollection', features };
  const source = map.getSource(INFORME_AREA_OUTLINE_SOURCE) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
  } else {
    map.addSource(INFORME_AREA_OUTLINE_SOURCE, { type: 'geojson', data });
  }
  if (!map.getLayer(INFORME_AREA_OUTLINE_LAYER)) {
    map.addLayer({
      id: INFORME_AREA_OUTLINE_LAYER,
      type: 'line',
      source: INFORME_AREA_OUTLINE_SOURCE,
      paint: {
        'line-color': mapColorTokens.hFF9800,
        'line-width': 3,
        'line-opacity': 0.95,
      },
    });
  }
  if (!ajustar) return;
  const bbox = bboxDeGeometrias(geometrias);
  if (bbox) {
    map.fitBounds(bbox, { padding: 64, duration: 600, maxZoom: 14 });
  }
}

/** Remove the Revisar-step outline (back to Elegir, or drawer close). */
export function quitarContornoSeleccion(map: maplibregl.Map): void {
  if (map.getLayer(INFORME_AREA_OUTLINE_LAYER)) map.removeLayer(INFORME_AREA_OUTLINE_LAYER);
  if (map.getSource(INFORME_AREA_OUTLINE_SOURCE)) map.removeSource(INFORME_AREA_OUTLINE_SOURCE);
}

/** Geometry payload type used by the outline (GeoJSON polygonal geometries). */
export type GeometriaZona = Polygon | MultiPolygon;
