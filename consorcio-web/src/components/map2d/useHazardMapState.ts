import { useEffect, useRef, type MutableRefObject } from 'react';
import type maplibregl from 'maplibre-gl';

import { useHazardUrlState } from '../../hooks/useHazardUrlState';
import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import { useMultiHazardGate } from '../../hooks/useMultiHazardGate';
import { useHazardMapStore } from '../../stores/hazardMapStore';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { syncHazardRiskLayers, syncPrecipNormalLayer } from './mapRasterOverlayHelpers';

export const HAZARD_CANONICAL_LAYER_IDS = [
  'flood_risk',
  'drainage_need',
  'soil',
  'canales_relevados',
  'basins',
  'precip_normal',
] as const;

interface VisibilitySnapshot {
  readonly values: Record<string, boolean>;
}

export interface UseHazardMapStateParams {
  readonly mapRef: MutableRefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly allGeoLayers?: readonly GeoLayerInfo[];
  readonly fichaActive?: boolean;
}

/**
 * Coordinates the inert multi-hazard lifecycle until the B3b map shell mounts it.
 *
 * The shared layer store owns durable visibility preferences. This hook captures
 * those values once at hazard entry, writes only the canonical hazard stack, and
 * restores the captured values on a genuine exit. It never re-applies defaults
 * while the mode remains active, so ordinary layer toggles stay under user control.
 */
export function useHazardMapState({
  mapRef,
  mapReady,
  allGeoLayers = [],
  fichaActive = false,
}: UseHazardMapStateParams) {
  const gateOpen = useMultiHazardGate();
  const url = useHazardUrlState();
  const isHazardActive = gateOpen && url.hazard;
  const snapshotRef = useRef<VisibilitySnapshot | null>(null);
  const wasHazardActiveRef = useRef(false);

  const visibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const panelOpen = useHazardMapStore((state) => state.panelOpen);
  const mobileExpanded = useHazardMapStore((state) => state.mobileExpanded);
  const pendingBasinZoom = useHazardMapStore((state) => state.pendingBasinZoom);
  const setPanelOpen = useHazardMapStore((state) => state.setPanelOpen);
  const setMobileExpanded = useHazardMapStore((state) => state.setMobileExpanded);
  const minimizeForFicha = useHazardMapStore((state) => state.minimizeForFicha);
  const reset = useHazardMapStore((state) => state.reset);

  useEffect(() => {
    const wasHazardActive = wasHazardActiveRef.current;

    if (isHazardActive && !wasHazardActive) {
      snapshotRef.current = { values: { ...visibleVectors } };
      for (const layerId of HAZARD_CANONICAL_LAYER_IDS) {
        setVectorVisibility('map2d', layerId, true);
      }
    }

    if (!isHazardActive && wasHazardActive && snapshotRef.current) {
      const snapshotValues = snapshotRef.current.values;
      for (const layerId of HAZARD_CANONICAL_LAYER_IDS) {
        setVectorVisibility('map2d', layerId, snapshotValues[layerId] ?? false);
      }
      for (const [layerId, visible] of Object.entries(snapshotValues)) {
        if (
          !HAZARD_CANONICAL_LAYER_IDS.includes(
            layerId as (typeof HAZARD_CANONICAL_LAYER_IDS)[number]
          )
        ) {
          setVectorVisibility('map2d', layerId, visible);
        }
      }
      snapshotRef.current = null;
      reset();
    }

    wasHazardActiveRef.current = isHazardActive;
  }, [isHazardActive, reset, setVectorVisibility, visibleVectors]);

  useEffect(() => {
    if (fichaActive && isHazardActive) minimizeForFicha();
  }, [fichaActive, isHazardActive, minimizeForFicha]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    syncPrecipNormalLayer(map, {
      isHazardActive,
      precipMonth: url.precipMonth,
      allGeoLayers,
    });
    syncHazardRiskLayers(map, {
      isHazardActive,
      activeRiskClasses: url.riskClasses,
      allGeoLayers,
    });
  }, [allGeoLayers, isHazardActive, mapReady, mapRef, url.precipMonth, url.riskClasses]);

  return {
    gateOpen,
    isHazardActive,
    url,
    panelOpen,
    setPanelOpen,
    mobileExpanded,
    setMobileExpanded,
    pendingBasinZoom,
    showPrecipitation: isHazardActive,
  };
}
