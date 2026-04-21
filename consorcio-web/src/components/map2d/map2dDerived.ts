import type { Feature, FeatureCollection } from 'geojson';
import { WATERWAY_DEFS } from '../../hooks/useWaterways';
import { getSoilColor } from '../../hooks/useSoilMap';
import { decorateFeature } from './map2dUtils';

export function buildSuggestedZonesDisplay(
  basins: FeatureCollection | null | undefined,
  draftBasinAssignments: Record<string, string>,
  suggestedZoneNames: Record<string, string>,
): FeatureCollection | null {
  if (!basins) return null;

  return {
    type: 'FeatureCollection',
    features: basins.features
      .filter((feature) => feature.properties?.draft_zone_id)
      .map((feature) => {
        const zoneId = String(feature.properties?.draft_zone_id ?? '');
        const effectiveZoneId = draftBasinAssignments[String(feature.properties?.id ?? '')] ?? zoneId;
        const colors: Record<string, string> = {
          Norte: '#9C27B0',
          'Monte Leña': '#4CAF50',
          Candil: '#2196F3',
        };
        const zoneName = suggestedZoneNames[effectiveZoneId] ?? String(feature.properties?.nombre ?? effectiveZoneId);
        const color = colors[zoneName] ?? '#1971c2';
        return decorateFeature(feature, { __color: color, __zone_id: effectiveZoneId });
      }),
  };
}

export function buildInitialDraftAssignments(suggestedZones: FeatureCollection | null | undefined) {
  const mapping: Record<string, string> = {};
  for (const feature of suggestedZones?.features ?? []) {
    const zoneId = String(feature.properties?.draft_zone_id || '');
    const memberIds = Array.isArray(feature.properties?.member_basin_ids)
      ? (feature.properties?.member_basin_ids as unknown[])
      : [];
    for (const basinId of memberIds) {
      if (typeof basinId === 'string' && zoneId) mapping[basinId] = zoneId;
    }
  }
  return mapping;
}

export function buildZoneDefinitionById(suggestedZones: FeatureCollection | null | undefined) {
  const mapping: Record<string, { defaultName: string; family: string | null; color: string }> = {};
  for (const feature of suggestedZones?.features ?? []) {
    const zoneId = String(feature.properties?.draft_zone_id || '');
    if (!zoneId) continue;
    mapping[zoneId] = {
      defaultName: String(feature.properties?.nombre || 'Zona sugerida'),
      family: (feature.properties?.family as string | undefined) ?? null,
      color: (feature.properties?.__color as string | undefined) || '#1971c2',
    };
  }
  return mapping;
}

export function buildBasinFeatureById(basins: FeatureCollection | null | undefined) {
  const mapping: Record<string, Feature> = {};
  for (const feature of basins?.features ?? []) {
    const basinId = feature.properties?.id;
    if (typeof basinId === 'string') mapping[basinId] = feature as Feature;
  }
  return mapping;
}

export function buildSuggestedZoneSummaries(
  zoneDefinitionById: Record<string, { defaultName: string; family: string | null; color: string }>,
  effectiveBasinAssignments: Record<string, string>,
  basinFeatureById: Record<string, Feature>,
) {
  return Object.entries(zoneDefinitionById).map(([zoneId, zoneDef]) => {
    let basinCount = 0;
    let superficieHa = 0;
    for (const [basinId, assignedZoneId] of Object.entries(effectiveBasinAssignments)) {
      if (assignedZoneId !== zoneId) continue;
      basinCount += 1;
      superficieHa += Number(basinFeatureById[basinId]?.properties?.superficie_ha || 0);
    }
    return {
      id: zoneId,
      defaultName: zoneDef.defaultName,
      family: zoneDef.family,
      basinCount,
      superficieHa,
    };
  });
}

function pushApprovedZoneLegendItems(
  items: Array<{ color: string; label: string; type: string }>,
  approvedZones: FeatureCollection,
) {
  for (const feature of approvedZones.features) {
    items.push({
      color: (feature.properties?.__color as string | undefined) || '#1971c2',
      label: String(feature.properties?.nombre || 'Cuenca'),
      type: 'fill',
    });
  }
}

function pushSoilLegendItems(
  items: Array<{ color: string; label: string; type: string }>,
  soilMap: FeatureCollection,
) {
  const capOrder = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII'];
  const presentCaps = new Set<string>();
  for (const feature of soilMap.features) {
    const cap = (feature.properties as { cap?: string | null } | null)?.cap;
    if (!cap) continue;
    const normalized = cap.trim().toUpperCase();
    const match = normalized.match(/^(VIII|VII|VI|IV|III|II|I)/);
    if (match) presentCaps.add(match[1]);
  }
  for (const cap of capOrder) {
    if (presentCaps.has(cap)) {
      items.push({ color: getSoilColor(cap), label: `Clase ${cap}`, type: 'fill' });
    }
  }
}

function pushWaterwayLegendItems(items: Array<{ color: string; label: string; type: string }>) {
  const waterwayEntries = WATERWAY_DEFS.map((waterway) => ({
    color: waterway.style.color,
    label: waterway.nombre,
  }));
  for (const entry of waterwayEntries) {
    items.push({ ...entry, type: 'line' });
  }
}

export function buildActiveLegendItems(params: {
  zonaCollection: FeatureCollection | null;
  vectorVisibility: Record<string, boolean>;
  hasApprovedZones: boolean;
  approvedZones: FeatureCollection | null | undefined;
  basins: FeatureCollection | null | undefined;
  soilMap: FeatureCollection | null | undefined;
}) {
  const { zonaCollection, vectorVisibility, hasApprovedZones, approvedZones, basins, soilMap } = params;

  const items: Array<{ color: string; label: string; type: string }> = [];

  if (zonaCollection && zonaCollection.features.length > 0) {
    items.push({ color: '#FF0000', label: 'Zona Consorcio', type: 'border' });
  }

  if (vectorVisibility.approved_zones && hasApprovedZones && approvedZones) {
    pushApprovedZoneLegendItems(items, approvedZones);
  }

  if (vectorVisibility.basins && basins && basins.features.length > 0) {
    items.push({ color: '#00897B', label: 'Subcuencas operativas', type: 'border' });
  }

  if (vectorVisibility.soil && soilMap && soilMap.features.length > 0) {
    pushSoilLegendItems(items, soilMap);
  }

  if (vectorVisibility.waterways) {
    pushWaterwayLegendItems(items);
  }

  return items;
}

export function buildVectorLayerItems(params: {
  basins: FeatureCollection | null | undefined;
  approvedZonesCollection: FeatureCollection | null | undefined;
  roadsCollection: FeatureCollection | null | undefined;
  intersectionsLength: number;
  isAdmin: boolean;
  /**
   * Whether the Pilar Verde static data has loaded (at least one slot non-null).
   * Callers can simply pass `!!pilarVerde?.aggregates` or similar — the flag
   * decides whether the 5 Pilar Verde toggles render in the layer control.
   * Defaults to `false` for backwards compatibility (no behavior change for
   * existing callers that haven't wired Pilar Verde yet).
   */
  showPilarVerde?: boolean;
  /**
   * Whether the Pilar Azul (Canales) static data has loaded (at least
   * `index.json` non-null). When true, the 2 master toggles render in the
   * layer control. Per-canal sub-toggles are rendered by Phase 4.
   */
  showPilarAzul?: boolean;
  /**
   * Whether the Pilar Azul (Escuelas rurales) static data has loaded
   * (collection non-null). When true, the single "Escuelas rurales" master
   * toggle renders in the layer control. There are NO per-school sub-toggles
   * — one master covers all 7 features (design §7). Defaults to `false` for
   * backwards compatibility (callers who haven't wired `useEscuelas` yet
   * see no behavior change).
   */
  showEscuelas?: boolean;
}) {
  const {
    basins,
    approvedZonesCollection,
    roadsCollection,
    intersectionsLength,
    isAdmin,
    showPilarVerde = false,
    showPilarAzul = false,
    showEscuelas = false,
  } = params;

  return [
    {
      id: 'basins',
      label: 'Subcuencas',
      show: isAdmin && !!basins && basins.features.length > 0,
    },
    { id: 'approved_zones', label: 'Cuencas', show: !!approvedZonesCollection },
    { id: 'waterways', label: 'Hidrografía', show: true },
    { id: 'roads', label: 'Red vial', show: !!roadsCollection && roadsCollection.features.length > 0 },
    { id: 'soil', label: 'Suelos IDECOR', show: true },
    { id: 'catastro', label: 'Catastro rural', show: true },
    { id: 'puntos_conflicto', label: 'Puntos conflicto', show: intersectionsLength > 0 },
    // ── Pilar Verde (Phase 2/7) — Spanish (Rioplatense) labels per spec ──
    {
      id: 'pilar_verde_bpa_historico',
      label: 'BPA histórico (por años)',
      show: showPilarVerde,
    },
    { id: 'pilar_verde_agro_aceptada', label: 'Agroforestal: Cumplen', show: showPilarVerde },
    { id: 'pilar_verde_agro_presentada', label: 'Agroforestal: Presentaron', show: showPilarVerde },
    { id: 'pilar_verde_agro_zonas', label: 'Zonas Agroforestales', show: showPilarVerde },
    {
      id: 'pilar_verde_porcentaje_forestacion',
      label: '% Forestación obligatoria',
      show: showPilarVerde,
    },
    // ── Pilar Azul (Canales) — master toggles per spec ──
    // Per-canal sub-toggles + the "Etapas propuestas" filter subsection are
    // rendered by Phase 4's `LayerControlsPanel` Canales section.
    { id: 'canales_relevados', label: 'Canales relevados', show: showPilarAzul },
    { id: 'canales_propuestos', label: 'Canales propuestos', show: showPilarAzul },
    // ── Pilar Azul (Escuelas rurales) — single master toggle (design §7) ──
    { id: 'escuelas', label: 'Escuelas rurales', show: showEscuelas },
  ]
    .filter(({ show }) => show)
    .map(({ id, label }) => ({ id, label }));
}

export function buildDemLayerOptions(
  demLayers: Array<{ id: string; tipo: string; nombre: string }>,
  geoLayerLabels: Record<string, string>,
) {
  return demLayers.map((layer) => ({
    value: layer.id,
    label: geoLayerLabels[layer.tipo] ?? layer.nombre,
  }));
}
