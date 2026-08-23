/**
 * useRoadFlowInteraction — the two map gestures of the cruces capability
 * (flujo-caminos, S4 wiring).
 *
 *   · CLICK ON A CROSSING  → open the field-survey sheet for ITS SEGMENT.
 *   · SELECT A LIST ROW    → recentre the map on that crossing.
 *
 * ⚠️ WHY THE CROSSING POINT IS "the road segment on the map". ⚠️
 * `tramo_ref` is the identity of a `red_vial` row, and the ONLY map feature in
 * this application that carries one is a crossing point: the public `caminos`
 * projection the "Red Vial" layer draws is a different dataset (roads coloured
 * by consorcio caminero, `useCaminosColoreados`) and has no `tramo_ref` at all.
 * So the crossing — a point that sits ON a red-vial segment and names it — is
 * the segment's representation here. Wiring the survey to the `roads` layer
 * instead would have to invent a mapping between two datasets, which is exactly
 * the kind of second copy of an identity this change refuses everywhere else.
 *
 * The panel's per-row "Relevar" button exists for the same reason from the
 * other direction: hitting an 8 px circle on a phone held on a rural road is
 * not an entry point, and RSS-R3's whole premise is that this is used in the
 * field.
 */

import type maplibregl from 'maplibre-gl';
import { type RefObject, useCallback, useEffect } from 'react';

import type { RoadFlowCrossingFeature } from '../../lib/api/roadFlow';
import { ROAD_FLOW_LAYER_IDS } from './roadFlowLayers';

/** Zoom the map settles on when a list row recentres it. */
export const ROAD_FLOW_FLY_TO_ZOOM = 15;

interface UseRoadFlowInteractionParams {
  readonly mapRef: RefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  /** Mirrors the layer toggle: no layer, no click target, no listener. */
  readonly active: boolean;
  /** Receives the clicked crossing's `tramo_ref`. */
  readonly onSelectTramo: (tramoRef: string) => void;
}

export interface UseRoadFlowInteractionResult {
  /** Recentre on one crossing. Safe before the map exists (no-op). */
  readonly flyToCrossing: (feature: RoadFlowCrossingFeature) => void;
}

/** Read a `tramo_ref` out of whatever MapLibre handed us, or `null`. */
export function readTramoRef(feature: unknown): string | null {
  const properties = (feature as { properties?: Record<string, unknown> } | null)?.properties;
  const value = properties?.tramo_ref;
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function useRoadFlowInteraction({
  mapRef,
  mapReady,
  active,
  onSelectTramo,
}: UseRoadFlowInteractionParams): UseRoadFlowInteractionResult {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !active) return;

    const handler = (event: { features?: unknown[] }) => {
      const tramoRef = readTramoRef(event.features?.[0]);
      if (tramoRef) onSelectTramo(tramoRef);
    };

    // One listener per layer id: `on(type, layerId, listener)` with a single id
    // is the form every MapLibre 4.x release supports, and the two ids belong
    // to one registry entry anyway.
    const layerIds = [ROAD_FLOW_LAYER_IDS.FLUJO, ROAD_FLOW_LAYER_IDS.CANAL];
    for (const layerId of layerIds) {
      map.on('click', layerId, handler as never);
    }
    return () => {
      for (const layerId of layerIds) {
        map.off('click', layerId, handler as never);
      }
    };
  }, [active, mapReady, mapRef, onSelectTramo]);

  const flyToCrossing = useCallback(
    (feature: RoadFlowCrossingFeature) => {
      const map = mapRef.current;
      const coordinates = feature.geometry?.coordinates;
      if (!map || !Array.isArray(coordinates) || coordinates.length < 2) return;
      const [lng, lat] = coordinates;
      if (!Number.isFinite(lng) || !Number.isFinite(lat)) return;
      map.flyTo({ center: [lng, lat], zoom: ROAD_FLOW_FLY_TO_ZOOM });
    },
    [mapRef]
  );

  return { flyToCrossing };
}
