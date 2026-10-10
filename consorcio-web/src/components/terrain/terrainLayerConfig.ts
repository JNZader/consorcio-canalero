import type { GeoLayerInfo } from '../../hooks/useGeoLayers';
import { PILAR_VERDE_LAYER_IDS } from '../../stores/mapLayerSyncStore';
import { LAYER_CATEGORY, type LayerCategory } from '../map2d/map2dDerived';

export type Terrain3DLayerStatus = 'supported' | 'planned' | 'not_supported_yet';

export interface Terrain3DRasterLayerConfig {
  readonly tipo: string;
  readonly status: Terrain3DLayerStatus;
}

export interface Terrain3DVectorLayerConfig {
  readonly id: string;
  readonly label: string;
  readonly status: Terrain3DLayerStatus;
}

export const SUPPORTED_3D_RASTER_TYPES: Terrain3DRasterLayerConfig[] = [
  { tipo: 'dem_raw', status: 'supported' },
  { tipo: 'slope', status: 'supported' },
  { tipo: 'aspect', status: 'supported' },
  { tipo: 'flow_dir', status: 'supported' },
  { tipo: 'flow_acc', status: 'supported' },
  { tipo: 'twi', status: 'supported' },
  { tipo: 'hand', status: 'supported' },
  { tipo: 'profile_curvature', status: 'supported' },
  { tipo: 'tpi', status: 'supported' },
  { tipo: 'terrain_class', status: 'supported' },
  { tipo: 'flood_risk', status: 'supported' },
  { tipo: 'drainage_need', status: 'supported' },
];

// NOTE: the "Zona Consorcio" toggle was removed from the 3D vector config —
// the 3D mesh IS the consorcio area, so the red perimeter outline that the
// toggle used to control was redundant visual noise. 2D keeps its own
// "Zona Consorcio" toggle via `LayerControlsPanel`, untouched by this change.
export const PRIORITY_3D_VECTOR_LAYERS: Terrain3DVectorLayerConfig[] = [
  { id: 'approved_zones', label: 'Cuencas', status: 'supported' },
  { id: 'basins', label: 'Subcuencas', status: 'supported' },
  { id: 'roads', label: 'Red Vial', status: 'supported' },
  { id: 'waterways', label: 'Hidrografía', status: 'supported' },
  { id: 'soil', label: 'Suelos IDECOR 1:50.000', status: 'supported' },
  { id: 'catastro', label: 'Catastro rural IDECOR', status: 'supported' },
  // Mirror of the 2D map's "Puntos conflicto" toggle — only meaningful
  // when the user is authenticated AND the backend reports intersections.
  // The panel hides this row when ``intersectionsLength === 0`` (see the
  // ``hiddenByContext`` check below).
  { id: 'puntos_conflicto', label: 'Puntos conflicto', status: 'supported' },
];

/** 2D catalog rows the 3D mesh cannot draw (UX PDF T1). Shown grayed. */
export const UNSUPPORTED_3D_VECTOR_LAYERS: Terrain3DVectorLayerConfig[] = [
  { id: 'red_vial_oficial', label: 'Catálogo IDECOR (no en Red Vial)', status: 'not_supported_yet' },
  { id: 'caminos_huecos', label: 'Caminos no catalogados (OSM/IGN)', status: 'not_supported_yet' },
  { id: 'road_flow', label: 'Cruces de camino', status: 'not_supported_yet' },
  { id: 'sentido_camino', label: 'Sentido en camino', status: 'not_supported_yet' },
  { id: 'puntos_interes', label: 'Puntos de interés', status: 'not_supported_yet' },
  { id: 'escuelas', label: 'Escuelas rurales', status: 'not_supported_yet' },
];

const supportedRasterTypeSet = new Set(
  SUPPORTED_3D_RASTER_TYPES.filter((layer) => layer.status === 'supported').map(
    (layer) => layer.tipo
  )
);

export function getSupported3DRasterLayers(layers: GeoLayerInfo[]): GeoLayerInfo[] {
  return layers.filter((layer) => supportedRasterTypeSet.has(layer.tipo));
}

/**
 * Category map for the 3D vector rows, so the 3D badge can reuse the SAME
 * derivation as 2D (`buildFamilyActiveCounts`). The ids are 3D-panel rows; the
 * categories mirror the 2D families the same layer belongs to.
 */
const TERRAIN_3D_LAYER_CATEGORIES: Record<string, LayerCategory> = {
  approved_zones: LAYER_CATEGORY.HIDROGRAFIA,
  basins: LAYER_CATEGORY.HIDROGRAFIA,
  waterways: LAYER_CATEGORY.HIDROGRAFIA,
  roads: LAYER_CATEGORY.TERRITORIO,
  soil: LAYER_CATEGORY.TERRITORIO,
  catastro: LAYER_CATEGORY.TERRITORIO,
  puntos_conflicto: LAYER_CATEGORY.ANALISIS,
};

/**
 * The rows `TerrainLayerTogglesPanel` actually renders, shaped as the
 * `layerItems` input of `buildFamilyActiveCounts` (T3c final round, R2-002).
 *
 * The 3D chrome has no `buildVectorLayerItems` of its own — its rows come from
 * `PRIORITY_3D_VECTOR_LAYERS` plus the 5 Pilar Verde toggles — so this is the
 * adapter that lets the 3D "N capas activas" badge count EXACTLY the rows the
 * panel shows instead of every raw `vectorLayerVisibility` key (which counts
 * the ~43 per-canal and 5 per-waterway sub-keys the panel never lists as rows).
 *
 * Differences from 2D, on purpose:
 *   - No BASE family: the 3D chrome has no IGN/DEM overlay checkboxes; its
 *     raster overlay is a single-choice Select, not a toggle.
 *   - `canales_relevados` / `canales_propuestos` are omitted here exactly like
 *     in 2D — `buildFamilyActiveCounts` counts the CANALES family from its
 *     visible children (`canalChildIds`), never from the master flags.
 */
export const PILAR_VERDE_ITEMS = [
  { id: 'pilar_verde_bpa_historico', label: 'BPA histórico (por años)' },
  { id: 'pilar_verde_agro_aceptada', label: 'Agroforestal: Cumplen' },
  { id: 'pilar_verde_agro_presentada', label: 'Agroforestal: Presentaron' },
  { id: 'pilar_verde_agro_zonas', label: 'Zonas Agroforestales' },
  { id: 'pilar_verde_porcentaje_forestacion', label: '% Forestación obligatoria' },
] as const;

const UNSUPPORTED_3D_LAYER_CATEGORIES: Record<string, LayerCategory> = {
  red_vial_oficial: LAYER_CATEGORY.TERRITORIO,
  caminos_huecos: LAYER_CATEGORY.TERRITORIO,
  escuelas: LAYER_CATEGORY.TERRITORIO,
  road_flow: LAYER_CATEGORY.ANALISIS,
  sentido_camino: LAYER_CATEGORY.ANALISIS,
  puntos_interes: LAYER_CATEGORY.ANALISIS,
};

export function buildTerrainLayerControlItems(params: {
  intersectionsLength?: number;
}): Array<{ id: string; label: string; category: LayerCategory }> {
  const { intersectionsLength = 0 } = params;
  const items: Array<{ id: string; label: string; category: LayerCategory }> = [];
  for (const layer of PRIORITY_3D_VECTOR_LAYERS) {
    if (layer.id === 'puntos_conflicto' && intersectionsLength === 0) continue;
    const category = TERRAIN_3D_LAYER_CATEGORIES[layer.id];
    if (category) items.push({ id: layer.id, label: layer.label, category });
  }
  for (const layer of UNSUPPORTED_3D_VECTOR_LAYERS) {
    const category = UNSUPPORTED_3D_LAYER_CATEGORIES[layer.id];
    if (category) items.push({ id: layer.id, label: layer.label, category });
  }
  for (const item of PILAR_VERDE_ITEMS) {
    items.push({ id: item.id, label: item.label, category: LAYER_CATEGORY.PILAR_VERDE });
  }
  return items;
}

export function buildTerrain3DLayerItems(params: {
  intersectionsLength?: number;
  showPilarVerde?: boolean;
}): Array<{ id: string; category: LayerCategory }> {
  const { intersectionsLength = 0, showPilarVerde = true } = params;
  const items: Array<{ id: string; category: LayerCategory }> = [];
  for (const layer of PRIORITY_3D_VECTOR_LAYERS) {
    // The panel hides this row when the backend reports no intersections.
    if (layer.id === 'puntos_conflicto' && intersectionsLength === 0) continue;
    const category = TERRAIN_3D_LAYER_CATEGORIES[layer.id];
    if (category) items.push({ id: layer.id, category });
  }
  if (showPilarVerde) {
    for (const id of PILAR_VERDE_LAYER_IDS) {
      items.push({ id, category: LAYER_CATEGORY.PILAR_VERDE });
    }
  }
  return items;
}
