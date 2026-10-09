import type { Map as MapLibreMap } from 'maplibre-gl';
import { type RefObject, useEffect, useRef } from 'react';

import {
  MAP2D_CATALOG_VECTOR_IDS,
  useMapLayerSyncStore,
} from '../../stores/mapLayerSyncStore';
import { parseMapPermalink, serializeMapPermalink } from './mapPermalink';
import type { MapPresetId } from './mapPresets';

interface UseMapPermalinkParams {
  readonly mapRef: RefObject<MapLibreMap | null>;
  readonly mapReady: boolean;
  readonly showDemOverlay: boolean;
  readonly activeDemLayerId: string | null;
  readonly setShowDemOverlay: (visible: boolean) => void;
  readonly setActiveDemLayerId: (id: string | null) => void;
  readonly demLayers: ReadonlyArray<{ id: string; tipo: string }>;
}

const WRITE_DEBOUNCE_MS = 400;
const catalog = new Set(MAP2D_CATALOG_VECTOR_IDS);

function applyPermalinkLayers(layers: string[] | undefined, preset: MapPresetId | undefined): void {
  const store = useMapLayerSyncStore.getState();
  if (preset) {
    store.applyPreset('map2d', preset);
    return;
  }
  if (!layers) return;
  store.hideAllCatalogLayers('map2d');
  for (const id of layers) {
    if (catalog.has(id)) store.setVectorVisibility('map2d', id, true);
  }
}

/**
 * Shareable `/mapa` query: camera, preset, catalog layers, raster tipo.
 * Preserves unrelated params (report lat/lng/zoom included).
 */
export function useMapPermalink({
  mapRef,
  mapReady,
  showDemOverlay,
  activeDemLayerId,
  setShowDemOverlay,
  setActiveDemLayerId,
  demLayers,
}: UseMapPermalinkParams): void {
  const appliedRef = useRef(false);
  const rasterAppliedRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined' || appliedRef.current) return;

    const run = () => {
      if (appliedRef.current) return;
      appliedRef.current = true;
      const parsed = parseMapPermalink(window.location.search);
      applyPermalinkLayers(parsed.layers, parsed.preset);
    };

    const persist = useMapLayerSyncStore.persist;
    if (persist?.hasHydrated?.()) run();
    else persist?.onFinishHydration?.(run);
    const timer = window.setTimeout(run, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || rasterAppliedRef.current) return;
    const parsed = parseMapPermalink(window.location.search);
    if (!parsed.rasterTipo) {
      rasterAppliedRef.current = true;
      return;
    }
    const layer = demLayers.find((item) => item.tipo === parsed.rasterTipo);
    if (!layer) return;
    rasterAppliedRef.current = true;
    setActiveDemLayerId(layer.id);
    setShowDemOverlay(true);
  }, [demLayers, setActiveDemLayerId, setShowDemOverlay]);

  useEffect(() => {
    if (!mapReady || typeof window === 'undefined') return;
    const map = mapRef.current;
    if (!map) return;

    let timeout = 0;
    const write = () => {
      const store = useMapLayerSyncStore.getState();
      const preset = store.presetByView.map2d;
      const layers = MAP2D_CATALOG_VECTOR_IDS.filter((id) => store.map2d.visibleVectors[id]);
      const rasterTipo = showDemOverlay
        ? demLayers.find((item) => item.id === activeDemLayerId)?.tipo
        : undefined;
      const center = map.getCenter();
      const next = serializeMapPermalink(
        window.location.search,
        {
          lat: center.lat,
          lng: center.lng,
          zoom: map.getZoom(),
          preset: preset && preset !== 'custom' ? preset : undefined,
          layers: preset && preset !== 'custom' ? undefined : layers,
          rasterTipo,
        },
        MAP2D_CATALOG_VECTOR_IDS
      );
      const url = `${window.location.pathname}${next}${window.location.hash}`;
      window.history.replaceState(window.history.state, '', url);
    };

    const schedule = () => {
      window.clearTimeout(timeout);
      timeout = window.setTimeout(write, WRITE_DEBOUNCE_MS);
    };

    map.on('moveend', schedule);
    const unsub = useMapLayerSyncStore.subscribe(schedule);
    schedule();
    return () => {
      window.clearTimeout(timeout);
      map.off('moveend', schedule);
      unsub();
    };
  }, [activeDemLayerId, demLayers, mapReady, mapRef, showDemOverlay]);
}
