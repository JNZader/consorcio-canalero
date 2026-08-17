import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';
import {
  HAZARD_DEFAULT_LAYERS,
  HAZARD_DEFAULT_PRECIP_MONTH,
  HAZARD_DEFAULT_RISK_CLASSES,
  RISK_CLASS_LABELS,
  type HazardUrlState,
  type RiskClass,
  useHazardUrlState,
} from '../../hooks/useHazardUrlState';
import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import { useMultiHazardGate } from '../../hooks/useMultiHazardGate';
import { useHazardMapStore } from '../../stores/hazardMapStore';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import { buildBasinCatastroFilter, findBasinById } from './hazardBasinFilter';
import { SOURCE_IDS } from './map2dConfig';
import { syncHazardRiskLayers, syncPrecipNormalLayer } from './mapRasterOverlayHelpers';
import { getFeatureCollectionBounds } from './map2dUtils';

const CANONICAL_STACK = [...HAZARD_DEFAULT_LAYERS];
const CANONICAL_STACK_SET = new Set<string>(CANONICAL_STACK);

/**
 * Snapshot of non-hazard vector visibility taken when hazard mode turns on.
 * Restored when hazard mode turns off.
 */
interface VisibilitySnapshot {
  readonly values: Record<string, boolean>;
}

export interface HazardMapState {
  /** Whether the feature flag + role gate is open. */
  gateOpen: boolean;
  /** Whether hazard mode is active (gate passes AND URL hazard=1). */
  isHazardActive: boolean;
  /** Whether hazard mode is requested in the URL (gate-independent). */
  hazard: boolean;
  /** Full URL-state API (setters + parsed values) for controls. */
  url: HazardUrlState;
  /** Currently selected basin feature (null when showing all). */
  selectedBasin: Feature<Geometry> | undefined;
  /** Toggle one risk class on/off. */
  toggleRiskClass: (label: RiskClass) => void;
  /** Desktop panel open state + setter. */
  panelOpen: boolean;
  setPanelOpen: (open: boolean) => void;
  /** Mobile expanded state + setter. */
  mobileExpanded: boolean;
  setMobileExpanded: (expanded: boolean) => void;
  /** True while a basin flyTo is in flight. */
  pendingBasinZoom: boolean;
  /** Whether the precipitation raster layer is currently visible. */
  showPrecipitation: boolean;
  /** MapLibre filter expression for the catastro layer, or null when no basin is selected. */
  catastroFilter: maplibregl.FilterSpecification | null;
  /** Whether some risk classes are hidden (used by the panel hint). */
  someRiskClassesHidden: boolean;
}

function normalizeRiskClasses(classes: RiskClass[]): RiskClass[] {
  return classes.length > 0 ? classes : [...HAZARD_DEFAULT_RISK_CLASSES];
}

/**
 * Encapsulates Multi-Hazard mode state and side effects for MapaMapLibre.
 *
 * Responsibilities:
 * - Gate + URL state
 * - Apply/restore canonical layer stack on mode toggle
 * - Resolve selected basin feature
 * - Trigger basin zoom + catastro filter
 * - Sync the precip_normal raster overlay
 * - Minimize panels when the ficha opens
 */
export function useHazardMapState(params: {
  mapRef: React.MutableRefObject<maplibregl.Map | null>;
  mapReady: boolean;
  basins: FeatureCollection | null | undefined;
  allGeoLayers: GeoLayerInfo[];
  fichaActive: boolean;
}): HazardMapState {
  const { mapRef, mapReady, basins, allGeoLayers, fichaActive } = params;

  const gateOpen = useMultiHazardGate();
  const hazard = useHazardUrlState();
  const {
    basin,
    setBasin,
    riskClasses,
    setRiskClasses,
    precipMonth,
    setPrecipMonth,
  } = hazard;
  const {
    panelOpen,
    mobileExpanded,
    pendingBasinZoom,
    setPanelOpen,
    setMobileExpanded,
    setPendingBasinZoom,
    minimizeForFicha,
    reset: resetHazardStore,
  } = useHazardMapStore();

  const isHazardActive = gateOpen && hazard.isHazardActive;

  // Snapshot of vector visibility taken the first time hazard mode turns on,
  // so we can restore it when the mode turns off.
  const snapshotRef = useRef<VisibilitySnapshot | null>(null);
  const setSharedVectorVisibility = useMapLayerSyncStore(
    (state) => state.setVectorVisibility
  );
  const sharedVisibleVectors = useMapLayerSyncStore((state) => state.map2d.visibleVectors);
  const setSharedVectorVisibilityRef = useRef(setSharedVectorVisibility);
  setSharedVectorVisibilityRef.current = setSharedVectorVisibility;
  const sharedVisibleVectorsRef = useRef(sharedVisibleVectors);
  sharedVisibleVectorsRef.current = sharedVisibleVectors;
  const resetHazardStoreRef = useRef(resetHazardStore);
  resetHazardStoreRef.current = resetHazardStore;
  const setRiskClassesRef = useRef(setRiskClasses);
  setRiskClassesRef.current = setRiskClasses;
  const setPrecipMonthRef = useRef(setPrecipMonth);
  setPrecipMonthRef.current = setPrecipMonth;
  const riskClassesRef = useRef(riskClasses);
  riskClassesRef.current = riskClasses;
  const precipMonthRef = useRef(precipMonth);
  precipMonthRef.current = precipMonth;

  // Apply canonical stack when hazard mode turns on; restore snapshot when off.
  // Intentionally keyed only on `isHazardActive` so user layer toggles while the
  // mode is active are not overwritten by the canonical defaults.
  useEffect(() => {
    if (!isHazardActive) {
      if (snapshotRef.current) {
        const restored = snapshotRef.current.values;
        // Restore each key individually through the shared store so the map
        // layer effects pick up the change.
        for (const [key, value] of Object.entries(restored)) {
          setSharedVectorVisibilityRef.current('map2d', key, value);
        }
        snapshotRef.current = null;
      }
      resetHazardStoreRef.current();
      return;
    }

    if (!snapshotRef.current) {
      snapshotRef.current = { values: { ...sharedVisibleVectorsRef.current } };
    }

    // Turn canonical stack ON. Layers not in the canonical stack keep their
    // previous state from the snapshot if one exists, otherwise their current
    // value. This avoids stomping user choices when re-enabling hazard mode.
    const base = snapshotRef.current?.values ?? sharedVisibleVectorsRef.current;
    for (const layerId of CANONICAL_STACK) {
      setSharedVectorVisibilityRef.current('map2d', layerId, true);
    }
    // Make sure non-canonical layers stay as they were (the snapshot already
    // holds their pre-hazard state; writing canonical ON is the only change).
    for (const [layerId, value] of Object.entries(base)) {
      if (!CANONICAL_STACK_SET.has(layerId)) {
        setSharedVectorVisibilityRef.current('map2d', layerId, value);
      }
    }

    // Default risk classes / precip month if missing.
    if (riskClassesRef.current.length === 0) {
      setRiskClassesRef.current([...HAZARD_DEFAULT_RISK_CLASSES]);
    }
    if (!precipMonthRef.current) {
      setPrecipMonthRef.current(HAZARD_DEFAULT_PRECIP_MONTH);
    }
  }, [isHazardActive]);

  // Minimize panels when a parcel ficha opens.
  useEffect(() => {
    if (fichaActive && isHazardActive) {
      minimizeForFicha();
    }
  }, [fichaActive, isHazardActive, minimizeForFicha]);

  // Resolve selected basin feature.
  const selectedBasin = useMemo(
    () => (isHazardActive ? findBasinById(basins, basin) : undefined),
    [isHazardActive, basins, basin]
  );

  // Unknown basin ids are dropped from the URL so the written state stays clean.
  // Only do this once basins have finished loading; otherwise the first render
  // clears a valid URL basin before the catalog arrives.
  useEffect(() => {
    if (!isHazardActive || !basin || !basins) return;
    if (!selectedBasin) {
      setBasin(null);
    }
  }, [isHazardActive, basin, selectedBasin, setBasin, basins]);

  // Fly to basin bbox when selection changes.
  const prevBasinRef = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !isHazardActive) return;

    const basinId = basin;
    if (basinId === prevBasinRef.current) return;
    prevBasinRef.current = basinId ?? null;

    if (!selectedBasin) {
      setPendingBasinZoom(false);
      return;
    }

    const bbox = getFeatureCollectionBounds({
      type: 'FeatureCollection',
      features: [selectedBasin],
    });
    if (!bbox) {
      setPendingBasinZoom(false);
      return;
    }

    setPendingBasinZoom(true);
    try {
      map.fitBounds(bbox, { padding: 40, duration: 800 });
      const clearPending = () => setPendingBasinZoom(false);
      map.once('moveend', clearPending);
      // Safety timeout in case moveend never fires (e.g. map frozen).
      const timeout = window.setTimeout(clearPending, 1500);
      return () => {
        map.off('moveend', clearPending);
        window.clearTimeout(timeout);
      };
    } catch {
      setPendingBasinZoom(false);
    }
  }, [mapRef, mapReady, isHazardActive, basin, selectedBasin, setPendingBasinZoom]);

  // Sync precip_normal raster overlay.
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    syncPrecipNormalLayer(map, {
      isHazardActive,
      precipMonth,
      allGeoLayers,
    });
  }, [mapRef, mapReady, isHazardActive, precipMonth, allGeoLayers]);

  // Sync flood_risk / drainage_need raster overlays.
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    syncHazardRiskLayers(map, {
      isHazardActive,
      activeRiskClasses: riskClasses,
      allGeoLayers,
    });
  }, [mapRef, mapReady, isHazardActive, riskClasses, allGeoLayers]);

  // Apply/remove the basin-driven filter on the catastro vector layer.
  const catastroFilter = useMemo(() => {
    if (!isHazardActive || !selectedBasin) return null;
    return buildBasinCatastroFilter(selectedBasin);
  }, [isHazardActive, selectedBasin]);

  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map) return;
    const fillLayer = `${SOURCE_IDS.CATASTRO}-fill`;
    const lineLayer = `${SOURCE_IDS.CATASTRO}-line`;
    if (map.getLayer(fillLayer)) {
      map.setFilter(fillLayer, catastroFilter ?? undefined);
    }
    if (map.getLayer(lineLayer)) {
      map.setFilter(lineLayer, catastroFilter ?? undefined);
    }
  }, [mapRef, mapReady, catastroFilter]);

  const toggleRiskClass = useCallback(
    (label: RiskClass) => {
      const next = riskClasses.includes(label)
        ? riskClasses.filter((c) => c !== label)
        : [...riskClasses, label];
      setRiskClasses(normalizeRiskClasses(next));
    },
    [riskClasses, setRiskClasses]
  );

  const someRiskClassesHidden = useMemo(
    () => riskClasses.length > 0 && riskClasses.length < RISK_CLASS_LABELS.length,
    [riskClasses.length]
  );

  const showPrecipitation = isHazardActive;

  return {
    gateOpen,
    isHazardActive,
    hazard: hazard.hazard,
    url: hazard,
    selectedBasin,
    toggleRiskClass,
    panelOpen,
    setPanelOpen,
    mobileExpanded,
    setMobileExpanded,
    pendingBasinZoom,
    showPrecipitation,
    catastroFilter,
    someRiskClassesHidden,
  };
}
