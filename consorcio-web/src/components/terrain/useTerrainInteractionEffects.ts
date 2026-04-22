/**
 * useTerrainInteractionEffects
 *
 * Strict mirror of the 2D `useMapInteractionEffects` (specifically the
 * feature-click branch — we do NOT port the asset-marking or basin-draft
 * branches, which are 2D-only workflows) for the 3D terrain viewer.
 *
 * Why a dedicated hook (vs inlining inside `TerrainViewer3D.tsx`):
 *   1. `TerrainViewer3D.tsx` is already > 500 lines — inlining the click
 *      handler (+ its bbox math + its layer-filter step) keeps the viewer
 *      readable.
 *   2. Matches the Batch B / Batch C precedent (`useTerrainPilarVerdeEffects`
 *      + `useTerrainCanalesEffects`) — one dedicated hook per concern.
 *   3. The hook surface accepts `mapRef` + `ready` + `setSelectedFeatures`
 *      so it has zero coupling to the top-level hooks; pure, testable.
 *
 * Click semantics:
 *   - Uses `queryRenderedFeatures` over a `±5px` BBOX (NOT a single point)
 *     — lines under `pitch=60` are flaky with single-point queries; a small
 *     pixel buffer raises the hit rate without breaking z-order precedence.
 *   - Filters `buildClickableLayers3D()` down to layers that exist on the
 *     map (MapLibre throws if `layers` contains unknown ids).
 *   - Stores the FULL feature list in `selectedFeatures` (top-most first,
 *     per MapLibre z-order) so `<InfoPanel>` can stack one section per
 *     feature — same contract as the 2D `setSelectedFeatures` pathway.
 *
 * @see `consorcio-web/src/components/map2d/useMapInteractionEffects.ts`
 *      — the 2D blueprint this mirrors verbatim.
 */

import type { Feature } from 'geojson';
import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect } from 'react';

import { buildClickableLayers3D, filterExistingLayers } from './terrainViewer3DUtils';

export interface UseTerrainInteractionEffectsParams {
  /** Ref to the mounted MapLibre instance. `null` before `setReady(true)`. */
  readonly mapRef: RefObject<maplibregl.Map | null>;
  /** `ready` flag from the viewer — gates the click handler until map is loaded. */
  readonly ready: boolean;
  /**
   * Setter for the viewer's `selectedFeatures` state. Receives the FULL
   * feature array MapLibre returned at the click bbox (top-most first).
   * Empty array clears the panel.
   */
  readonly setSelectedFeatures: (features: Feature[]) => void;
}

export function useTerrainInteractionEffects({
  mapRef,
  ready,
  setSelectedFeatures,
}: UseTerrainInteractionEffectsParams): void {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    const handleClick = (event: maplibregl.MapMouseEvent) => {
      // ±5px bbox around the click point. Raises hit-rate for thin line
      // layers (canales) at pitch=60 without breaking parcel precedence
      // because MapLibre still returns features in z-order within the
      // bbox (top-most first).
      const { x, y } = event.point;
      const bbox: [[number, number], [number, number]] = [
        [x - 5, y - 5],
        [x + 5, y + 5],
      ];

      const layers = filterExistingLayers(map, buildClickableLayers3D());
      const features = map.queryRenderedFeatures(bbox, { layers });

      // Surface ALL overlapping features — matches the 2D InfoPanel
      // stacking contract. When the array is empty the panel unmounts.
      setSelectedFeatures(features as unknown as Feature[]);
    };

    map.on('click', handleClick);
    return () => {
      map.off('click', handleClick);
    };
  }, [mapRef, ready, setSelectedFeatures]);
}
