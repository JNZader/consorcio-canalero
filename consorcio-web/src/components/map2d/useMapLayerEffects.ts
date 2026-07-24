import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';
import type { Dispatch, RefObject, SetStateAction } from 'react';
import { useEffect } from 'react';
import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { useMapLayerSyncStore } from '../../stores/mapLayerSyncStore';
import type { CanalesData, Etapa } from '../../types/canales';
import { ALL_ETAPAS } from '../../types/canales';
import type { EscuelasData } from '../../types/escuelas';
import type { PilarVerdeData } from '../../types/pilarVerde';
import { applyLayerOpacity, applyLayerOrder } from './layerRenderRegistry';
import {
  shouldShowSuggestedZones,
  syncAgroAceptadaLayer,
  syncAgroPresentadaLayer,
  syncAgroZonasLayer,
  syncApprovedZoneLayers,
  syncBaseTileVisibility,
  syncBasinLayers,
  syncBpaHistoricoLayer,
  syncCanalesLayers,
  syncEscuelasLayer,
  syncPorcentajeForestacionLayer,
  syncRoadLayers,
  syncSoilLayers,
  syncSuggestedZoneLayers,
  syncWaterwayLayers,
  syncYpfEstacionBombeoLayer,
  syncZonaLayer,
} from './mapLayerEffectHelpers';
import { syncCatastroLayers } from './mapLayerEffectHelpers';
import {
  getVisibleRasterLayersForDem,
  moveDemAboveContextualVectors,
  syncDemRasterLayer,
  syncIgnLayer,
  syncImageOverlays,
  syncMartinSuggestionLayers,
} from './mapRasterOverlayHelpers';

interface LayerLike {
  id: string;
  nombre: string;
  tipo: string;
}

interface UseMapLayerEffectsParams {
  mapRef: RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  baseLayer: 'osm' | 'satellite';
  isAdmin: boolean;
  vectorVisibility: Record<string, boolean>;
  soilCollection: FeatureCollection | null;
  roadsCollection: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  zonaCollection: FeatureCollection | null;
  approvedZonesCollection: FeatureCollection | null | undefined;
  suggestedZonesDisplay: FeatureCollection | null;
  showSuggestedZonesPanel: boolean;
  hasApprovedZones: boolean;
  activeDemLayerId: string | null;
  showDemOverlay: boolean;
  demTileUrl: string | null;
  allGeoLayers: LayerLike[];
  setVisibleRasterLayers: Dispatch<SetStateAction<Array<{ tipo: string }>>>;
  showIGNOverlay: boolean;
  viewMode: 'base' | 'single' | 'comparison';
  selectedImage: { tile_url: string } | null;
  comparison: {
    left?: { tile_url: string } | null;
    right?: { tile_url: string } | null;
  } | null;
  waterwaysDefs: readonly (typeof WATERWAY_DEFS)[number][];
  /**
   * Pilar Verde static data. `undefined` means the parent has not wired the
   * hook yet; `null` slots are tolerated (graceful degradation — sync helpers
   * fall back to an empty FeatureCollection and stay hidden).
   */
  pilarVerde?: PilarVerdeData | null;
  /**
   * Pilar Azul (Canales) static data. Same graceful-degradation contract as
   * Pilar Verde — `undefined` means not-wired-yet, `null` slots stay hidden.
   */
  canales?: Partial<CanalesData> | null;
  /**
   * Pilar Azul (Escuelas rurales) static data. Same graceful-degradation
   * contract: `undefined` means not-wired-yet; `collection: null` means
   * fetch failed and the layer mounts an empty source.
   */
  escuelas?: Partial<EscuelasData> | null;
}

export function useMapLayerEffects({
  mapRef,
  mapReady,
  baseLayer,
  isAdmin,
  vectorVisibility,
  soilCollection,
  roadsCollection,
  basins,
  zonaCollection,
  approvedZonesCollection,
  suggestedZonesDisplay,
  showSuggestedZonesPanel,
  hasApprovedZones,
  activeDemLayerId,
  showDemOverlay,
  demTileUrl,
  allGeoLayers,
  setVisibleRasterLayers,
  showIGNOverlay,
  viewMode,
  selectedImage,
  comparison,
  waterwaysDefs,
  pilarVerde,
  canales,
  escuelas,
}: UseMapLayerEffectsParams) {
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncBaseTileVisibility(map, baseLayer);
  }, [baseLayer, mapReady, mapRef]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncWaterwayLayers(map, waterwaysDefs, !!vectorVisibility.waterways);
  }, [mapReady, mapRef, vectorVisibility.waterways, waterwaysDefs]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncSoilLayers(map, soilCollection, !!vectorVisibility.soil);
  }, [mapReady, mapRef, soilCollection, vectorVisibility.soil]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncCatastroLayers(map, !!vectorVisibility.catastro);
  }, [mapReady, mapRef, vectorVisibility.catastro]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncRoadLayers(map, roadsCollection, !!vectorVisibility.roads);
  }, [mapReady, mapRef, roadsCollection, vectorVisibility.roads]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    // Subcuencas (basins) is admin-only — gate the rendering as well as the
    // toggle so a non-admin with a stale persisted vectorVisibility cannot
    // see the layer.
    syncBasinLayers(map, basins, isAdmin && !!vectorVisibility.basins);
  }, [basins, isAdmin, mapReady, mapRef, vectorVisibility.basins]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncZonaLayer(map, zonaCollection);
  }, [mapReady, mapRef, zonaCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncApprovedZoneLayers(map, approvedZonesCollection, !!vectorVisibility.approved_zones);
  }, [approvedZonesCollection, mapReady, mapRef, vectorVisibility.approved_zones]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncSuggestedZoneLayers(
      map,
      suggestedZonesDisplay,
      shouldShowSuggestedZones({
        showSuggestedZonesPanel,
        hasApprovedZones,
        suggestedZonesDisplay,
      })
    );
  }, [hasApprovedZones, mapReady, mapRef, showSuggestedZonesPanel, suggestedZonesDisplay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncDemRasterLayer(map, { showDemOverlay, activeDemLayerId, demTileUrl });
  }, [activeDemLayerId, demTileUrl, mapReady, mapRef, showDemOverlay]);

  useEffect(() => {
    const nextLayers = getVisibleRasterLayersForDem(allGeoLayers, showDemOverlay, activeDemLayerId);
    setVisibleRasterLayers((prev) => {
      if (prev.length === nextLayers.length && prev[0]?.tipo === nextLayers[0]?.tipo) {
        return prev;
      }
      return nextLayers;
    });
  }, [activeDemLayerId, allGeoLayers, setVisibleRasterLayers, showDemOverlay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncIgnLayer(map, showIGNOverlay);
  }, [mapReady, mapRef, showIGNOverlay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncImageOverlays(map, { baseLayer, viewMode, selectedImage, comparison });
  }, [baseLayer, comparison, mapReady, mapRef, selectedImage, viewMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncMartinSuggestionLayers(map, {
      showConflictPoints: !!vectorVisibility.puntos_conflicto,
    });
  }, [mapReady, mapRef, vectorVisibility.puntos_conflicto]);

  // ── Pilar Verde (Phase 2) ───────────────────────────────────────────────
  // Each layer has a dedicated effect so a change to one collection doesn't
  // cause all five to rerun. The helpers are idempotent, so re-running on
  // visibility changes is safe.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = pilarVerde?.bpaHistorico ?? null;
    syncBpaHistoricoLayer(
      map,
      data as FeatureCollection | null,
      !!vectorVisibility.pilar_verde_bpa_historico
    );
  }, [mapReady, mapRef, pilarVerde?.bpaHistorico, vectorVisibility.pilar_verde_bpa_historico]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = pilarVerde?.agroAceptada ?? null;
    syncAgroAceptadaLayer(
      map,
      data as FeatureCollection | null,
      !!vectorVisibility.pilar_verde_agro_aceptada
    );
  }, [mapReady, mapRef, pilarVerde?.agroAceptada, vectorVisibility.pilar_verde_agro_aceptada]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = pilarVerde?.agroPresentada ?? null;
    syncAgroPresentadaLayer(
      map,
      data as FeatureCollection | null,
      !!vectorVisibility.pilar_verde_agro_presentada
    );
  }, [mapReady, mapRef, pilarVerde?.agroPresentada, vectorVisibility.pilar_verde_agro_presentada]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = pilarVerde?.agroZonas ?? null;
    syncAgroZonasLayer(
      map,
      data as FeatureCollection | null,
      !!vectorVisibility.pilar_verde_agro_zonas
    );
  }, [mapReady, mapRef, pilarVerde?.agroZonas, vectorVisibility.pilar_verde_agro_zonas]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const data = pilarVerde?.porcentajeForestacion ?? null;
    syncPorcentajeForestacionLayer(
      map,
      data as FeatureCollection | null,
      !!vectorVisibility.pilar_verde_porcentaje_forestacion
    );
  }, [
    mapReady,
    mapRef,
    pilarVerde?.porcentajeForestacion,
    vectorVisibility.pilar_verde_porcentaje_forestacion,
  ]);

  // ── Pilar Azul (Canales — Phase 2) ─────────────────────────────────────
  // Bootstrap: when `index.json` resolves, register the dynamic per-canal
  // ids into the store. Idempotent — re-running preserves user-flipped
  // values via the persist middleware.
  const registerPilarAzul = useMapLayerSyncStore((s) => s.registerPilarAzul);
  useEffect(() => {
    if (!canales?.index) return;
    registerPilarAzul(canales.index);
  }, [canales?.index, registerPilarAzul]);

  // Subscribe to the propuestas-etapas slice so the layer filter re-runs
  // whenever the user toggles an etapa.
  const propuestasEtapasVisibility = useMapLayerSyncStore((s) => s.propuestasEtapasVisibility);

  // ── Canales visibility signature ─────────────────────────────────────────
  // The canales sync effect only cares about the canales-related slices of
  // `vectorVisibility` (master toggles + per-canal `canal_relevado_*` /
  // `canal_propuesto_*` keys). Depending on the whole object made EVERY
  // layer toggle (soil, roads, escuelas, …) re-filter and re-order the
  // canales z-stack. A sorted string signature gives value-equality in the
  // dep array (Object.is on strings), so the effect re-runs only when a
  // canales-relevant flag actually changes.
  const canalesVisibilitySignature = Object.entries(vectorVisibility)
    .filter(
      ([key]) =>
        key === 'canales_relevados' ||
        key === 'canales_propuestos' ||
        key.startsWith('canal_relevado_') ||
        key.startsWith('canal_propuesto_')
    )
    .map(([key, value]) => `${key}:${value ? 1 : 0}`)
    .sort()
    .join('|');
  const canalesRelevadosVisible = !!vectorVisibility.canales_relevados;
  const canalesPropuestosVisible = !!vectorVisibility.canales_propuestos;

  useEffect(() => {
    // Reference the signature so the effect re-runs on per-canal toggles
    // (the id lists below are read non-reactively via `getState()`).
    void canalesVisibilitySignature;
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!canales) return;

    // Compute per-canal visible id lists from the store state.
    // For relevados: include every registered canal whose per-canal flag is
    // not false. The master toggle gates the whole layer via visibility.
    const state = useMapLayerSyncStore.getState();
    const allRelevadoSlugs = (canales.index?.relevados ?? []).map((r) => r.id);
    const visibleRelevadoIds = allRelevadoSlugs.filter((slug) => {
      const key = `canal_relevado_${slug.replace(/-/g, '_')}`;
      return state.map2d.visibleVectors[key] !== false;
    });

    // Propuestas uses the store selector — it combines per-canal + etapa.
    const visiblePropuestaIds = state.getVisiblePropuestaIds('map2d');

    // Active etapas = keys with value `true`.
    const activeEtapas = (Object.entries(propuestasEtapasVisibility) as [Etapa, boolean][])
      .filter(([, v]) => v)
      .map(([k]) => k);

    syncCanalesLayers(map, {
      relevados: (canales.relevados ?? null) as FeatureCollection<
        GeoJSON.LineString,
        import('../../types/canales').CanalFeatureProperties
      > | null,
      propuestas: (canales.propuestas ?? null) as FeatureCollection<
        GeoJSON.LineString,
        import('../../types/canales').CanalFeatureProperties
      > | null,
      relevadosVisible: canalesRelevadosVisible,
      propuestasVisible: canalesPropuestosVisible,
      visibleRelevadoIds,
      visiblePropuestaIds,
      activeEtapas: activeEtapas.length > 0 ? activeEtapas : ALL_ETAPAS,
    });
  }, [
    mapReady,
    mapRef,
    canales,
    canales?.index,
    canales?.relevados,
    canales?.propuestas,
    canalesRelevadosVisible,
    canalesPropuestosVisible,
    canalesVisibilitySignature,
    propuestasEtapasVisibility,
  ]);

  // ── Pilar Azul (Escuelas rurales) ──────────────────────────────────────
  // Native MapLibre `circle` layer + companion text-only `symbol` layer for
  // the label. The sync helper is synchronous (no icon asset, no loadImage,
  // no Promise) — previous symbol+icon approach had two successive silent-
  // fail paths and was abandoned. See `escuelasLayers.ts` header for history.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const collection = (escuelas?.collection ?? null) as FeatureCollection<
      GeoJSON.Point,
      import('../../types/escuelas').EscuelaFeatureProperties
    > | null;
    syncEscuelasLayer(map, collection, !!vectorVisibility.escuelas);
  }, [mapReady, mapRef, escuelas?.collection, vectorVisibility.escuelas]);

  // ── YPF estación de bombeo (Monte Leña) ────────────────────────────────
  // Single hardcoded landmark — always-on, no toggle, no tear-down. The
  // sync helper is idempotent, so re-running on map-ready flips is safe.
  // Dep array is minimal on purpose: the data is a module-level constant,
  // so only the map identity + readiness matter.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncYpfEstacionBombeoLayer(map);
  }, [mapReady, mapRef]);

  // ── Per-layer opacity & order (map-redesign Fase 3) ─────────────────────
  // Read the map2d overrides. Both default to `{}` / `[]` (untouched), in
  // which case the apply helpers are guaranteed no-ops so the default
  // rendering stays byte-identical to before this feature existed.
  const opacityByLayer = useMapLayerSyncStore((s) => s.map2d.opacityByLayer);
  const orderByLayer = useMapLayerSyncStore((s) => s.map2d.orderByLayer);

  // Async-mount / re-hoist re-run signal (FF-A3). The opacity/order effects
  // apply IMPERATIVELY and skip ml layers that aren't mounted yet — so if a
  // target layer mounts AFTER the effect first ran (react-query data arrives,
  // e.g. waterways start as `[]`), or a sibling sync effect re-hoists the
  // stack via raise*Stack, a persisted override would be silently lost.
  // Collapsing every mount/reorder trigger into a string signature lets both
  // effects RE-RUN whenever the layer set or its ordering could have changed.
  // Over-firing is safe: the apply helpers are idempotent and no-op on empty
  // overrides (byte-identical default preserved). These effects are declared
  // AFTER the sync effects, so within a commit they run LAST and reassert the
  // custom order over any raise*Stack call.
  const layerMountSignal = [
    Object.entries(vectorVisibility)
      .map(([key, value]) => `${key}:${value ? 1 : 0}`)
      .sort()
      .join(','),
    soilCollection ? 1 : 0,
    roadsCollection ? 1 : 0,
    basins ? 1 : 0,
    zonaCollection ? 1 : 0,
    approvedZonesCollection ? 1 : 0,
    suggestedZonesDisplay ? 1 : 0,
    canales?.index ? 1 : 0,
    canales?.relevados ? 1 : 0,
    canales?.propuestas ? 1 : 0,
    escuelas?.collection ? 1 : 0,
    pilarVerde?.bpaHistorico ? 1 : 0,
    pilarVerde?.agroAceptada ? 1 : 0,
    pilarVerde?.agroPresentada ? 1 : 0,
    pilarVerde?.agroZonas ? 1 : 0,
    pilarVerde?.porcentajeForestacion ? 1 : 0,
    waterwaysDefs.length,
    Object.entries(propuestasEtapasVisibility)
      .map(([key, value]) => `${key}:${value ? 1 : 0}`)
      .sort()
      .join(','),
  ].join('|');

  // Opacity: for each UI id whose multiplier is PRESENT (incl. 1 → reset to
  // default), apply `default * clampedMultiplier` on its ml layers. An empty
  // override map has no entries → nothing applied → default untouched. Re-runs
  // on `layerMountSignal` so overrides land on layers that mount later.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    void layerMountSignal;
    applyLayerOpacity(map, opacityByLayer);
  }, [mapReady, mapRef, opacityByLayer, layerMountSignal]);

  // Order: when `orderByLayer` is non-empty, hoist each UI id's ml-layer group
  // to enforce the requested bottom → top order. Empty → no-op (today's
  // ordering, incl. PILAR_VERDE_Z_ORDER + roads-below-waterways, untouched).
  // Runs after the sync effects above have mounted/ordered the base stack, and
  // re-asserts the custom order after any raise*Stack re-hoist via the signal.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    void layerMountSignal;
    applyLayerOrder(map, orderByLayer);
  }, [mapReady, mapRef, orderByLayer, layerMountSignal]);

  // ── DEM z-order hoist ───────────────────────────────────────────────────
  // Keep the DEM raster just below the user-authored stack (Pilar Verde +
  // Canales) so contextual vectors (soil / catastro / basins / roads /
  // waterways) are NOT dimmed by the 0.6 raster-opacity overlay. This effect
  // must re-run whenever a sibling sync effect can have mounted/reordered a
  // reference layer — but ONLY while the DEM is actually shown. The previous
  // version depended on ~13 raw objects and re-ran on every layer toggle
  // even with the DEM off (immediate early-return). Instead we collapse all
  // mount/reorder triggers into a string signature that is a constant ''
  // while the DEM is inactive, so inactive-DEM renders never re-fire it.
  const demActive = showDemOverlay && !!activeDemLayerId;
  const demReorderSignal = !demActive
    ? ''
    : [
        // Any visibility flip can mount a layer above the DEM raster.
        Object.entries(vectorVisibility)
          .map(([key, value]) => `${key}:${value ? 1 : 0}`)
          .sort()
          .join(','),
        // Data arrival mounts sources/layers after the DEM is already up.
        soilCollection ? 1 : 0,
        roadsCollection ? 1 : 0,
        basins ? 1 : 0,
        canales?.index ? 1 : 0,
        canales?.relevados ? 1 : 0,
        canales?.propuestas ? 1 : 0,
        pilarVerde?.bpaHistorico ? 1 : 0,
        pilarVerde?.agroAceptada ? 1 : 0,
        pilarVerde?.agroPresentada ? 1 : 0,
        pilarVerde?.agroZonas ? 1 : 0,
        pilarVerde?.porcentajeForestacion ? 1 : 0,
        // Etapa flips re-run syncCanalesLayers (may remount canal layers).
        Object.entries(propuestasEtapasVisibility)
          .map(([key, value]) => `${key}:${value ? 1 : 0}`)
          .sort()
          .join(','),
      ].join('|');

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    if (!showDemOverlay || !activeDemLayerId) return;
    // `demReorderSignal` is referenced so sibling layer mounts/reorders
    // (encoded in the signature) re-trigger the hoist while the DEM is on.
    // `demTileUrl` is referenced because syncDemRasterLayer re-creates the
    // raster layer (appended on top) when the tile URL changes — the hoist
    // must re-run afterwards.
    void demReorderSignal;
    void demTileUrl;
    moveDemAboveContextualVectors(map);
  }, [mapReady, mapRef, showDemOverlay, activeDemLayerId, demTileUrl, demReorderSignal]);
}
