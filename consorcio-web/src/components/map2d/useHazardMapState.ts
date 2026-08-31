import { useEffect, useRef, type MutableRefObject } from 'react';
import type maplibregl from 'maplibre-gl';

import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import { useHazardUrlState } from '../../hooks/useHazardUrlState';
import { useMultiHazardGate } from '../../hooks/useMultiHazardGate';
import { useAuthLoading } from '../../stores/authStore';
import { useHazardMapStore } from '../../stores/hazardMapStore';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import type { HazardBasinOption } from './hazardControls.types';
import {
  HAZARD_NORMAL_VISIBILITY,
  clearHazardVisibilitySnapshot,
  readHazardVisibilitySnapshot,
  writeHazardVisibilitySnapshot,
} from './hazardVisibilitySnapshot';
import { getFeatureCollectionBounds } from './map2dUtils';
import {
  getVisibleHazardRasterLayers,
  syncHazardRiskLayers,
  syncPrecipNormalLayer,
} from './mapRasterOverlayHelpers';
import { getPrecipitationRange } from './precipRanges';

const NO_BASIN_OPTIONS: readonly HazardBasinOption[] = [];

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

type SetVectorVisibility = (view: 'map2d' | 'map3d', layerId: string, visible: boolean) => void;

/** Restore captured keys; canonical keys missing from the snapshot become hidden. */
function applyVisibilitySnapshot(
  values: Record<string, boolean>,
  setVectorVisibility: SetVectorVisibility
) {
  for (const layerId of HAZARD_CANONICAL_LAYER_IDS) {
    setVectorVisibility('map2d', layerId, values[layerId] ?? false);
  }
  for (const [layerId, visible] of Object.entries(values)) {
    if (
      !HAZARD_CANONICAL_LAYER_IDS.includes(layerId as (typeof HAZARD_CANONICAL_LAYER_IDS)[number])
    ) {
      setVectorVisibility('map2d', layerId, visible);
    }
  }
}

function applyCanonicalStack(setVectorVisibility: SetVectorVisibility) {
  for (const layerId of HAZARD_CANONICAL_LAYER_IDS) {
    setVectorVisibility('map2d', layerId, true);
  }
}

function visibilityMatchesSnapshot(
  current: Record<string, boolean>,
  snapshot: Record<string, boolean>
): boolean {
  for (const layerId of HAZARD_CANONICAL_LAYER_IDS) {
    if ((current[layerId] ?? false) !== (snapshot[layerId] ?? false)) return false;
  }
  return Object.entries(snapshot).every(([id, visible]) => (current[id] ?? false) === visible);
}

function rememberSnapshot(values: Record<string, boolean>): VisibilitySnapshot {
  const snapshot = { values: { ...values } };
  writeHazardVisibilitySnapshot(snapshot.values);
  return snapshot;
}

export interface UseHazardMapStateParams {
  readonly mapRef: MutableRefObject<maplibregl.Map | null>;
  readonly mapReady: boolean;
  readonly allGeoLayers?: readonly GeoLayerInfo[];
  readonly basinIds?: readonly string[];
  readonly basinOptions?: readonly HazardBasinOption[];
  readonly fichaActive?: boolean;
}

/**
 * Coordinates the inert multi-hazard lifecycle until the B3b map shell mounts it.
 *
 * The shared layer store owns durable visibility preferences. This hook captures
 * those values once at hazard entry, writes only the canonical hazard stack, and
 * restores the captured values on a genuine exit or on unmount while active. It never re-applies defaults
 * while the mode remains active, so ordinary layer toggles stay under user control.
 */
export function useHazardMapState({
  mapRef,
  mapReady,
  allGeoLayers = [],
  basinIds,
  basinOptions = NO_BASIN_OPTIONS,
  fichaActive = false,
}: UseHazardMapStateParams) {
  const gateOpen = useMultiHazardGate();
  const authPending = useAuthLoading();
  const url = useHazardUrlState({ basinIds });
  const isHazardActive = gateOpen && url.hazard;
  const snapshotRef = useRef<VisibilitySnapshot | null>(null);
  const wasHazardActiveRef = useRef(false);
  const hasResolvedAuthRef = useRef(false);

  const visibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setVectorVisibility = useMapLayerSyncStore((state) => state.setVectorVisibility);
  const panelOpen = useHazardMapStore((state) => state.panelOpen);
  const mobileExpanded = useHazardMapStore((state) => state.mobileExpanded);
  const pendingBasinZoom = useHazardMapStore((state) => state.pendingBasinZoom);
  const setPendingBasinZoom = useHazardMapStore((state) => state.setPendingBasinZoom);
  const setPanelOpen = useHazardMapStore((state) => state.setPanelOpen);
  const setMobileExpanded = useHazardMapStore((state) => state.setMobileExpanded);
  const minimizeForFicha = useHazardMapStore((state) => state.minimizeForFicha);
  const reset = useHazardMapStore((state) => state.reset);

  useEffect(() => {
    if (authPending) return;

    const wasHazardActive = wasHazardActiveRef.current;

    if (!hasResolvedAuthRef.current) {
      hasResolvedAuthRef.current = true;
      if (isHazardActive) {
        snapshotRef.current = rememberSnapshot(
          readHazardVisibilitySnapshot()?.values ?? { ...HAZARD_NORMAL_VISIBILITY }
        );
        if (visibilityMatchesSnapshot(visibleVectors, snapshotRef.current.values)) {
          applyCanonicalStack(setVectorVisibility);
        }
      } else {
        clearHazardVisibilitySnapshot();
        snapshotRef.current = null;
      }
      wasHazardActiveRef.current = isHazardActive;
      return;
    }

    if (isHazardActive && !wasHazardActive) {
      snapshotRef.current = rememberSnapshot(visibleVectors);
      applyCanonicalStack(setVectorVisibility);
    }

    if (!isHazardActive && wasHazardActive && snapshotRef.current) {
      applyVisibilitySnapshot(snapshotRef.current.values, setVectorVisibility);
      snapshotRef.current = null;
      clearHazardVisibilitySnapshot();
      reset();
    }

    wasHazardActiveRef.current = isHazardActive;
  }, [authPending, isHazardActive, reset, setVectorVisibility, visibleVectors]);

  // Unmount-only cleanup (JD-B3B-001): if the map shell unmounts while hazard
  // mode is still active, the transition branch above never runs — restore the
  // snapshot here so hazard-forced values never stay in the persisted store.
  // The nulled snapshot ref keeps this idempotent (no double-restore after an
  // active→inactive exit), and clearing `wasHazardActiveRef` lets a remount
  // (e.g. StrictMode replay) re-capture from the just-restored values.
  useEffect(() => {
    return () => {
      if (!wasHazardActiveRef.current || !snapshotRef.current) return;
      applyVisibilitySnapshot(
        snapshotRef.current.values,
        useMapLayerSyncStore.getState().setVectorVisibility
      );
      snapshotRef.current = null;
      wasHazardActiveRef.current = false;
    };
  }, []);

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

  // Basin zoom (B3b basin contract): a selected basin with readable geometry
  // drives ONE bounded fitBounds, bracketed by the pendingBasinZoom seam.
  // "Mostrar todo" (null basin) and missing/empty geometry are deliberate no-ops.
  useEffect(() => {
    const map = mapRef.current;
    if (!isHazardActive || !mapReady || !map || !url.basin) return;

    const geometry = basinOptions.find((option) => option.id === url.basin)?.geometry;
    if (!geometry) return;

    const bounds = getFeatureCollectionBounds({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', properties: {}, geometry }],
    });
    if (!bounds) return;

    // Responsive padding: 8% of the smaller viewport axis, clamped.
    const container = map.getContainer();
    const axis = Math.min(container.clientWidth, container.clientHeight);
    const padding = Math.min(96, Math.max(24, Math.round(axis * 0.08)));

    setPendingBasinZoom(true);
    const settle = () => setPendingBasinZoom(false);
    map.once('moveend', settle);
    map.fitBounds(bounds, { padding, maxZoom: 13, duration: 600 });

    return () => {
      map.off('moveend', settle);
      settle();
    };
  }, [basinOptions, isHazardActive, mapReady, mapRef, setPendingBasinZoom, url.basin]);

  const visibleRasterLayers = getVisibleHazardRasterLayers({
    allGeoLayers,
    isHazardActive,
    precipMonth: url.precipMonth,
  });
  const precipitationRange = visibleRasterLayers.some((layer) => layer.tipo === 'precip_normal')
    ? getPrecipitationRange(url.precipMonth)
    : null;

  return {
    gateOpen,
    isHazardActive,
    url,
    panelOpen,
    setPanelOpen,
    mobileExpanded,
    setMobileExpanded,
    pendingBasinZoom,
    precipitationRange,
    showPrecipitation: isHazardActive,
    visibleRasterLayers,
  };
}
