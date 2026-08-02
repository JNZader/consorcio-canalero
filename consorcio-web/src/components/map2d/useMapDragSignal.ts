/**
 * useMapDragSignal
 *
 * Emits a monotonically increasing counter every time the user STARTS DRAGGING
 * the map (T3a, fix 2 — auto-minimize).
 *
 * Only `dragstart` is subscribed, deliberately:
 *   - `click` already drives selection, and minimizing on the very click that
 *     opened a panel would make the panel unusable;
 *   - `zoom` fires on wheel/pinch and on every programmatic `fitBounds`, so
 *     minimizing there would collapse panels the app itself opened;
 *   - `move` fires continuously during the drag — one signal per gesture is all
 *     the consumer needs.
 *
 * A COUNTER rather than a boolean: the consumer wants "a drag just started"
 * as an event, and re-minimizing after the user restored a pill mid-pan must
 * work on the second drag too, which a latched boolean cannot express.
 *
 * SUBSCRIPTION CONTRACT. The effect reads `mapRef.current` but depends on
 * `[mapRef, mapReady]`: a ref's `.current` is not reactive, so swapping the map
 * INSTANCE alone would leave the listener on the dead map. That is safe here
 * only because the container guarantees the swap always cycles `mapReady`
 * (false while the new map initializes, true again on its `load`), which re-runs
 * the effect and re-subscribes. Any future caller that replaces the instance
 * without cycling `mapReady` breaks this hook.
 */

import type maplibregl from 'maplibre-gl';
import { type RefObject, useEffect, useState } from 'react';

/** The map event that arms the auto-minimize. Exported so tests pin the choice. */
export const MAP_DRAG_EVENT = 'dragstart';

export function useMapDragSignal(
  mapRef: RefObject<maplibregl.Map | null>,
  mapReady: boolean
): number {
  const [signal, setSignal] = useState(0);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;

    const onDragStart = () => setSignal((value) => value + 1);
    map.on(MAP_DRAG_EVENT, onDragStart);
    return () => {
      map.off(MAP_DRAG_EVENT, onDragStart);
    };
  }, [mapRef, mapReady]);

  return signal;
}
