import { useCallback, useEffect, useMemo, useRef, type MutableRefObject } from 'react';
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
import { useAuthLoading } from '../../stores/authStore';
import { useHazardMapStore } from '../../stores/hazardMapStore';
import { defaultVisibleVectors, useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import {
  clearHazardVisibilitySnapshot,
  readHazardVisibilitySnapshot,
  writeHazardVisibilitySnapshot,
} from './hazardVisibilitySnapshot';
import { buildBasinCatastroFilter, findBasinById } from './hazardBasinFilter';
import { SOURCE_IDS } from './map2dConfig';
import { syncHazardRiskLayers, syncPrecipNormalLayer } from './mapRasterOverlayHelpers';
import { getFeatureCollectionBounds } from './map2dUtils';

const CANONICAL_STACK = [...HAZARD_DEFAULT_LAYERS];
const CANONICAL_STACK_SET = new Set<string>(CANONICAL_STACK);

/**
 * True when every canonical hazard layer is currently visible in the shared
 * store. Used to distinguish a *genuine* hazard enable (pre-hazard state still
 * in the store) from a *reload of an already-applied hazard session* (the
 * canonical stack was persisted by a prior session and is already ON). The
 * latter is the exact case H4 fixes: we must NOT capture the canonical stack as
 * the pre-hazard restore source.
 */
function isCanonicalStackApplied(values: Record<string, boolean>): boolean {
  return CANONICAL_STACK.every((layerId) => values[layerId] === true);
}

/**
 * Restore the pre-hazard visibility snapshot into the shared store when hazard
 * mode turns off. Any canonical hazard layer absent from the snapshot was
 * forced ON by hazard mode, so it is explicitly turned OFF — this guarantees we
 * never leave the hazard stack visible after disabling (covers the fresh-shared
 * link fallback, whose snapshot is documented normal defaults and omits those
 * layers).
 */
function restorePreHazardSnapshot(
  snapshotRef: MutableRefObject<VisibilitySnapshot | null>,
  restore: (layerId: string, visible: boolean) => void
): void {
  const snapshot = snapshotRef.current;
  if (!snapshot) return;
  for (const [layerId, value] of Object.entries(snapshot.values)) {
    restore(layerId, value);
  }
  for (const layerId of CANONICAL_STACK) {
    if (!(layerId in snapshot.values)) {
      restore(layerId, false);
    }
  }
  snapshotRef.current = null;
}

/**
 * Hydrate the in-memory pre-hazard snapshot EXACTLY ONCE. Prefer a valid
 * sessionStorage snapshot written by a prior session in THIS tab (a reload while
 * hazard mode is still active preserves the user's pre-hazard state). Never
 * overwrite a valid stored snapshot with the canonical stack.
 *
 * When no snapshot exists, distinguish the two sub-cases: a genuine first enable
 * (store still holds the user's pre-hazard visibility → capture that) versus a
 * reload of an already-applied hazard session (canonical stack already in the
 * store → fall back to documented normal defaults, never the canonical stack).
 */
function hydratePreHazardSnapshot(
  snapshotRef: MutableRefObject<VisibilitySnapshot | null>,
  sharedVisibleVectors: Record<string, boolean>,
  normalDefaults: Record<string, boolean>
): Record<string, boolean> {
  if (snapshotRef.current) return snapshotRef.current.values;
  const stored = readHazardVisibilitySnapshot();
  if (stored) {
    snapshotRef.current = { values: { ...stored.values } };
    return stored.values;
  }
  const preHazard = isCanonicalStackApplied(sharedVisibleVectors)
    ? { ...normalDefaults }
    : { ...sharedVisibleVectors };
  snapshotRef.current = { values: preHazard };
  // Persist so a later remount / reload in this tab keeps the same restore
  // source and we never re-derive it from a now-canonical store state.
  writeHazardVisibilitySnapshot(preHazard);
  return preHazard;
}

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
  // Auth initialization gate. While `authLoading` is true the gate has not yet
  // resolved, so `isHazardActive === false` is NOT a genuine inactive state —
  // it is merely the gate being closed pending auth (see C6-R3-001 below).
  const authLoading = useAuthLoading();
  const authResolved = !authLoading;
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
  //
  // CRITICAL (C6-R3-001): `isHazardActive` is false BOTH when hazard mode is
  // genuinely off AND while auth initialization is still pending (the gate has
  // not resolved yet, so an authorized operator reloading with `?hazard=1` is
  // momentarily "inactive"). We must NOT touch the snapshot while auth is
  // loading — doing so would destroy a valid pre-hazard snapshot written by a
  // prior session in this tab (the user's original layer visibility) before the
  // gate opens. Only after auth resolves do we apply the lifecycle:
  //   - hazard active             → hydrate existing snapshot without overwrite;
  //   - genuine active→inactive   → restore + clear exactly once;
  //   - initial resolved non-hazard (never activated this session) →
  //     drop any stale snapshot WITHOUT restoring incorrect visibility.
  // Intentionally keyed only on `isHazardActive` + `authResolved` so user layer
  // toggles while the mode is active are not overwritten by canonical defaults.
  useEffect(() => {
    // Wait for auth to resolve before any snapshot lifecycle runs. While
    // `authLoading` is true the current `isHazardActive === false` is not a
    // real inactive state and must not clear/restore anything.
    if (!authResolved) return;

    if (!isHazardActive) {
      if (snapshotRef.current) {
        // Genuine active -> inactive transition this session: restore the
        // pre-hazard visibility exactly once and drop the persisted snapshot.
        restorePreHazardSnapshot(snapshotRef, (layerId, visible) =>
          setSharedVectorVisibilityRef.current('map2d', layerId, visible)
        );
        // Drop the persisted snapshot — hazard mode is over for this tab.
        clearHazardVisibilitySnapshot();
        resetHazardStoreRef.current();
        return;
      }
      // Initial resolved non-hazard state: we never activated hazard this
      // session. A stale snapshot left by a prior session must be dropped so it
      // cannot leak into a future restore, but we must NOT restore it (that
      // would apply pre-hazard visibility while not in hazard mode).
      clearHazardVisibilitySnapshot();
      return;
    }

    const base = hydratePreHazardSnapshot(
      snapshotRef,
      sharedVisibleVectorsRef.current,
      defaultVisibleVectors
    );

    // Turn canonical stack ON. Layers not in the canonical stack keep their
    // previous state from the snapshot if one exists, otherwise their current
    // value. This avoids stomping user choices when re-enabling hazard mode.
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
  }, [isHazardActive, authResolved]);

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
  //
  // CRITICAL (JD-A-1): a basin is marked "handled" ONLY after a zoom was
  // actually initiated. A shared URL carries `?basin=` before the async basin
  // catalog arrives, so on first render `selectedBasin` is still undefined. The
  // old code assigned `prevBasinRef` BEFORE checking `selectedBasin`, so by the
  // time the catalog loaded the effect believed it had already zoomed and
  // skipped `fitBounds` forever. We now leave the marker unset until the zoom
  // fires, so the delayed catalog triggers exactly one `fitBounds`.
  const zoomedBasinRef = useRef<string | null>(null);
  useEffect(() => {
    const map = mapRef.current;
    if (!mapReady || !map || !isHazardActive) return;

    const basinId = basin;

    // No basin selected → reset the marker and clear any pending zoom.
    if (!basinId) {
      zoomedBasinRef.current = null;
      setPendingBasinZoom(false);
      return;
    }

    // Already zoomed to this basin → don't repeat (handles re-renders / prop
    // churn that keep the same selection).
    if (basinId === zoomedBasinRef.current) return;

    // Basin id is set but the catalog hasn't resolved the feature yet (async
    // load). Wait — do NOT mark as handled, so the next effect run (after
    // `selectedBasin` arrives) triggers the zoom exactly once.
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

    // Mark handled BEFORE initiating the zoom so concurrent re-renders with
    // the same selection don't double-trigger `fitBounds`.
    zoomedBasinRef.current = basinId;
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
      // Zoom failed → allow a later retry once the selection is re-validated.
      zoomedBasinRef.current = null;
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
