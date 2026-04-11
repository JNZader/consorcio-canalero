import type { GeoLayerInfo } from '../../hooks/useGeoLayers';

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

export const PRIORITY_3D_VECTOR_LAYERS: Terrain3DVectorLayerConfig[] = [
  { id: 'approved_zones', label: 'Cuencas', status: 'supported' },
  { id: 'zona', label: 'Zona Consorcio', status: 'supported' },
  { id: 'basins', label: 'Subcuencas', status: 'supported' },
  { id: 'roads', label: 'Red Vial', status: 'supported' },
  { id: 'waterways', label: 'Hidrografía', status: 'supported' },
  { id: 'soil', label: 'Suelos IDECOR 1:50.000', status: 'supported' },
  { id: 'catastro', label: 'Catastro rural IDECOR', status: 'supported' },
];

const supportedRasterTypeSet = new Set(
  SUPPORTED_3D_RASTER_TYPES.filter((layer) => layer.status === 'supported').map((layer) => layer.tipo),
);

export function getSupported3DRasterLayers(layers: GeoLayerInfo[]): GeoLayerInfo[] {
  return layers.filter((layer) => supportedRasterTypeSet.has(layer.tipo));
}
