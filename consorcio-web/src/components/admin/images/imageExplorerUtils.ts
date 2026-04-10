import type { SelectedImage } from '../../../hooks/useSelectedImage';

export const MONTH_NAMES = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
] as const;

export const DAY_NAMES = ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'] as const;

export interface ImageResultLike {
  tile_url: string;
  target_date: string;
  dates_available: string[];
  images_count: number;
  visualization: string;
  visualization_description: string;
  sensor: string;
  collection: string;
  flood_info?: {
    id: string;
    name: string;
    date: string;
    description: string;
    severity: string;
  };
}

export interface VisualizationOption {
  id: string;
  description: string;
}

export function buildVisualizationOptions(
  sensor: 'sentinel2' | 'sentinel1',
  visualizations: VisualizationOption[],
) {
  if (sensor === 'sentinel2') {
    return visualizations.map((v) => ({ value: v.id, label: v.description }));
  }
  return [
    { value: 'vv', label: 'Radar SAR (VV)' },
    { value: 'vv_flood', label: 'Deteccion de agua (SAR)' },
  ];
}

export function createSelectedImageFromResult(
  result: ImageResultLike | null,
): SelectedImage | null {
  if (!result) return null;
  return {
    tile_url: result.tile_url,
    target_date: result.target_date,
    sensor: result.sensor as 'Sentinel-1' | 'Sentinel-2',
    visualization: result.visualization,
    visualization_description: result.visualization_description,
    collection: result.collection,
    images_count: result.images_count,
    flood_info: result.flood_info
      ? {
          id: result.flood_info.id,
          name: result.flood_info.name,
          description: result.flood_info.description,
          severity: result.flood_info.severity,
        }
      : undefined,
    selected_at: new Date().toISOString(),
  };
}
