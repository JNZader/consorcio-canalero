import type { FeatureCollection } from 'geojson';
import { useMemo } from 'react';
import { GEO_LAYER_LABELS, buildTileUrl } from '../../hooks/useGeoLayers';
import { getSoilColor } from '../../hooks/useSoilMap';
import { decorateFeature, asFeatureCollection } from './map2dUtils';
import {
  buildActiveLegendItems,
  buildBasinFeatureById,
  buildDemLayerOptions,
  buildInitialDraftAssignments,
  buildSuggestedZoneSummaries,
  buildSuggestedZonesDisplay,
  buildVectorLayerItems,
  buildZoneDefinitionById,
} from './map2dDerived';

interface GeoLayer {
  id: string;
  tipo: string;
  nombre: string;
}

export function useMapDerivedState(params: {
  capas: Record<string, FeatureCollection | undefined>;
  caminos: FeatureCollection | null | undefined;
  assets: Array<{ tipo: string; longitud: number; latitud: number } & object>;
  publicLayers: Array<{ id: string; data?: FeatureCollection | null }>;
  soilMap: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  suggestedZones: FeatureCollection | null | undefined;
  waterways: Array<{ nombre: string; style: { color?: string }; data: FeatureCollection }>;
  allGeoLayers: GeoLayer[];
  approvedZones: FeatureCollection | null | undefined;
  draftBasinAssignments: Record<string, string>;
  suggestedZoneNames: Record<string, string>;
  hiddenClasses: Record<string, number[]>;
  hiddenRanges: Record<string, number[]>;
  activeDemLayerId: string | null;
  selectedDraftBasinId: string | null;
  selectedImage: { sensor: string; target_date: string } | null;
  comparison: { left?: { target_date: string } | null; right?: { target_date: string } | null } | null;
  vectorVisibility: Record<string, boolean>;
  hasApprovedZones: boolean;
  intersectionsLength: number;
  isAdmin: boolean;
}) {
  const {
    capas,
    caminos,
    assets,
    publicLayers,
    soilMap,
    basins,
    suggestedZones,
    waterways,
    allGeoLayers,
    approvedZones,
    draftBasinAssignments,
    suggestedZoneNames,
    hiddenClasses,
    hiddenRanges,
    activeDemLayerId,
    selectedDraftBasinId,
    selectedImage,
    comparison,
    vectorVisibility,
    hasApprovedZones,
    intersectionsLength,
    isAdmin,
  } = params;

  const zonaCollection = capas.zona ?? null;
  const roadsCollection = caminos;

  const waterwaysCollection = useMemo((): FeatureCollection | null => {
    const features = waterways.flatMap((layer) =>
      layer.data.features.map((feature) =>
        decorateFeature(feature, { __color: layer.style.color ?? '#1565C0', __label: layer.nombre }),
      ),
    );
    return features.length > 0 ? asFeatureCollection(features) : null;
  }, [waterways]);

  const soilCollection = useMemo((): FeatureCollection | null => {
    if (!soilMap) return null;
    return asFeatureCollection(
      soilMap.features.map((feature) =>
        decorateFeature(feature, { __color: getSoilColor((feature.properties as { cap?: string | null } | null)?.cap) }),
      ),
    );
  }, [soilMap]);

  const infrastructureCollection = useMemo((): FeatureCollection | null => {
    const features = assets.map((asset) => {
      const color =
        asset.tipo === 'puente' ? '#f03e3e'
          : asset.tipo === 'alcantarilla' ? '#1971c2'
            : asset.tipo === 'canal' ? '#2f9e44'
              : '#fd7e14';
      return {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [asset.longitud, asset.latitud] },
        properties: { ...asset, __color: color },
      };
    });
    return features.length > 0 ? asFeatureCollection(features) : null;
  }, [assets]);

  const approvedZonesCollection = approvedZones;
  const suggestedZonesDisplay = useMemo(
    () => buildSuggestedZonesDisplay(basins, draftBasinAssignments, suggestedZoneNames),
    [basins, draftBasinAssignments, suggestedZoneNames],
  );

  const demTileUrl = useMemo(() => {
    if (!activeDemLayerId) return null;
    const layer = allGeoLayers.find((item) => item.id === activeDemLayerId);
    if (!layer) return null;
    return buildTileUrl(layer.id, {
      hideClasses: (hiddenClasses[layer.tipo] ?? []).length > 0 ? hiddenClasses[layer.tipo] : undefined,
      hideRanges: (hiddenRanges[layer.tipo] ?? []).length > 0 ? hiddenRanges[layer.tipo] : undefined,
    });
  }, [activeDemLayerId, allGeoLayers, hiddenClasses, hiddenRanges]);

  const compositeTypes = useMemo(() => new Set(['flood_risk', 'drainage_need']), []);
  const demLayers = useMemo(() => allGeoLayers.filter((layer) => !compositeTypes.has(layer.tipo)), [allGeoLayers, compositeTypes]);

  const initialDraftAssignments = useMemo(() => buildInitialDraftAssignments(suggestedZones), [suggestedZones]);
  const zoneDefinitionById = useMemo(() => buildZoneDefinitionById(suggestedZones), [suggestedZones]);
  const basinFeatureById = useMemo(() => buildBasinFeatureById(basins), [basins]);

  const effectiveBasinAssignments = useMemo(
    () => ({ ...initialDraftAssignments, ...draftBasinAssignments }),
    [draftBasinAssignments, initialDraftAssignments],
  );

  const suggestedZoneSummaries = useMemo(
    () => buildSuggestedZoneSummaries(zoneDefinitionById, effectiveBasinAssignments, basinFeatureById),
    [basinFeatureById, effectiveBasinAssignments, zoneDefinitionById],
  );

  const selectedDraftBasinName = useMemo(() => {
    if (!selectedDraftBasinId) return null;
    const feature = basinFeatureById[selectedDraftBasinId];
    return feature?.properties?.nombre ? String(feature.properties.nombre) : selectedDraftBasinId;
  }, [basinFeatureById, selectedDraftBasinId]);

  const selectedDraftBasinZoneId = useMemo(
    () => (selectedDraftBasinId ? (effectiveBasinAssignments[selectedDraftBasinId] ?? null) : null),
    [effectiveBasinAssignments, selectedDraftBasinId],
  );

  const activeLegendItems = useMemo(
    () =>
      buildActiveLegendItems({
        zonaCollection,
        vectorVisibility,
        hasApprovedZones,
        approvedZones,
        basins,
        soilMap,
        infrastructureCollection,
      }),
    [zonaCollection, vectorVisibility, hasApprovedZones, approvedZones, basins, soilMap, infrastructureCollection],
  );

  const hasSingleImage = !!selectedImage;
  const hasComparison = !!(comparison?.left && comparison.right);

  const singleImageInfo = useMemo(
    () => (selectedImage ? { sensor: selectedImage.sensor, date: selectedImage.target_date } : null),
    [selectedImage],
  );
  const comparisonInfo = useMemo(
    () =>
      comparison?.left && comparison.right
        ? { leftDate: comparison.left.target_date, rightDate: comparison.right.target_date }
        : null,
    [comparison],
  );

  const vectorLayerItems = useMemo(
    () =>
      buildVectorLayerItems({
        basins,
        approvedZonesCollection,
        roadsCollection,
        infrastructureCollection,
        publicLayersLength: publicLayers.length,
        intersectionsLength,
        isAdmin,
      }),
    [approvedZonesCollection, basins, infrastructureCollection, intersectionsLength, isAdmin, publicLayers.length, roadsCollection],
  );

  const demLayerOptions = useMemo(() => buildDemLayerOptions(demLayers, GEO_LAYER_LABELS), [demLayers]);

  return {
    zonaCollection,
    roadsCollection,
    waterwaysCollection,
    soilCollection,
    infrastructureCollection,
    approvedZonesCollection,
    suggestedZonesDisplay,
    demTileUrl,
    demLayers,
    effectiveBasinAssignments,
    suggestedZoneSummaries,
    selectedDraftBasinName,
    selectedDraftBasinZoneId,
    activeLegendItems,
    hasSingleImage,
    hasComparison,
    singleImageInfo,
    comparisonInfo,
    vectorLayerItems,
    demLayerOptions,
  };
}
