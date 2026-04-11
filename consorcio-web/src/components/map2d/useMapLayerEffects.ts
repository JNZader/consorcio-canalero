import type { FeatureCollection } from 'geojson';
import type maplibregl from 'maplibre-gl';
import type { Dispatch, RefObject, SetStateAction } from 'react';
import { useEffect } from 'react';
import type { WATERWAY_DEFS } from '../../hooks/useWaterways';
import {
  shouldShowSuggestedZones,
  syncApprovedZoneLayers,
  syncBaseTileVisibility,
  syncBasinLayers,
  syncInfrastructureLayer,
  syncPublicLayers,
  syncRoadLayers,
  syncSoilLayers,
  syncSuggestedZoneLayers,
  syncWaterwayLayers,
  syncZonaLayer,
} from './mapLayerEffectHelpers';
import {
  getVisibleRasterLayersForDem,
  syncDemRasterLayer,
  syncIgnLayer,
  syncImageOverlays,
  syncMartinSuggestionLayers,
} from './mapRasterOverlayHelpers';
import { syncCatastroLayers } from './mapLayerEffectHelpers';

interface LayerLike {
  id: string;
  nombre: string;
  tipo: string;
}

interface PublicLayerLike extends LayerLike {
  data?: FeatureCollection | null;
}

interface UseMapLayerEffectsParams {
  mapRef: RefObject<maplibregl.Map | null>;
  mapReady: boolean;
  baseLayer: 'osm' | 'satellite';
  vectorVisibility: Record<string, boolean>;
  soilCollection: FeatureCollection | null;
  roadsCollection: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  zonaCollection: FeatureCollection | null;
  approvedZonesCollection: FeatureCollection | null | undefined;
  suggestedZonesDisplay: FeatureCollection | null;
  showSuggestedZonesPanel: boolean;
  hasApprovedZones: boolean;
  infrastructureCollection: FeatureCollection | null;
  publicLayers: PublicLayerLike[];
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
}

export function useMapLayerEffects({
  mapRef,
  mapReady,
  baseLayer,
  vectorVisibility,
  soilCollection,
  roadsCollection,
  basins,
  zonaCollection,
  approvedZonesCollection,
  suggestedZonesDisplay,
  showSuggestedZonesPanel,
  hasApprovedZones,
  infrastructureCollection,
  publicLayers,
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
    syncBasinLayers(map, basins, !!vectorVisibility.basins);
  }, [basins, mapReady, mapRef, vectorVisibility.basins]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncZonaLayer(map, zonaCollection);
  }, [mapReady, mapRef, zonaCollection]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncApprovedZoneLayers(
      map,
      approvedZonesCollection,
      !!vectorVisibility.approved_zones,
    );
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
      }),
    );
  }, [hasApprovedZones, mapReady, mapRef, showSuggestedZonesPanel, suggestedZonesDisplay]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncInfrastructureLayer(
      map,
      infrastructureCollection,
      !!vectorVisibility.infrastructure,
    );
  }, [infrastructureCollection, mapReady, mapRef, vectorVisibility.infrastructure]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncPublicLayers(map, publicLayers, !!vectorVisibility.public_layers);
  }, [mapReady, mapRef, publicLayers, vectorVisibility.public_layers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    syncDemRasterLayer(map, { showDemOverlay, activeDemLayerId, demTileUrl });
  }, [activeDemLayerId, demTileUrl, mapReady, mapRef, showDemOverlay]);

  useEffect(() => {
    const nextLayers = getVisibleRasterLayersForDem(
      allGeoLayers,
      showDemOverlay,
      activeDemLayerId,
    );
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
}
