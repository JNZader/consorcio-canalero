import type { SatelliteSensorLabel, SelectedImage } from '../../../hooks/useSelectedImage';

export const MONTH_NAMES = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
] as const;

export const DAY_NAMES = ['Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sa', 'Do'] as const;

export type ImageSensor = 'sentinel2' | 'sentinel1' | 'landsat8' | 'landsat7' | 'landsat5';

export function sensorLabel(sensor: ImageSensor): SatelliteSensorLabel {
  const labels: Record<ImageSensor, SatelliteSensorLabel> = {
    sentinel2: 'Sentinel-2',
    sentinel1: 'Sentinel-1',
    landsat8: 'Landsat 8',
    landsat7: 'Landsat 7',
    landsat5: 'Landsat 5',
  };
  return labels[sensor];
}

export function isOpticalSensor(sensor: ImageSensor): boolean {
  return sensor !== 'sentinel1';
}

export interface ImageResultLike {
  tile_url: string;
  target_date: string;
  dates_available: string[];
  images_count: number;
  visualization: string;
  visualization_description: string;
  sensor: string;
  collection: string;
  notes?: string | null;
  composition_mode?: 'scene' | 'composite' | 'gapfill';
  days_buffer?: number | null;
  max_cloud?: number | null;
  cloud_cover?: number | null;
  path?: number | null;
  row?: number | null;
  label?: string;
  flood_info?: {
    id: string;
    name: string;
    date: string;
    description: string;
    severity: string;
  };
}

export type ImageSceneLike = ImageResultLike & {
  id: string;
  label: string;
};

export interface VisualizationOption {
  id: string;
  description: string;
}

export function buildVisualizationOptions(
  sensor: ImageSensor,
  visualizations: VisualizationOption[] | null | undefined
) {
  if (isOpticalSensor(sensor)) {
    const safeVisualizations = Array.isArray(visualizations) ? visualizations : [];
    return safeVisualizations.map((v, index) => ({
      value: v.id || `visualization-${index}`,
      label: v.description || v.id || `Visualizacion ${index + 1}`,
    }));
  }
  return [
    { value: 'vv', label: 'Radar SAR (VV)' },
    { value: 'vv_flood', label: 'Deteccion de agua (SAR)' },
  ];
}

export function createSelectedImageFromResult(
  result: ImageResultLike | null
): SelectedImage | null {
  if (!result) return null;
  // 'gapfill' and 'composite' both require mode=composite to regenerate the
  // same tile: the backend decides gap-fill vs pure median from data presence.
  const mode: 'scene' | 'composite' =
    result.composition_mode === 'composite' || result.composition_mode === 'gapfill'
      ? 'composite'
      : 'scene';
  return {
    tile_url: result.tile_url,
    target_date: result.target_date,
    sensor: result.sensor as SatelliteSensorLabel,
    visualization: result.visualization,
    visualization_description: result.visualization_description,
    collection: result.collection,
    images_count: result.images_count,
    days_buffer: typeof result.days_buffer === 'number' ? result.days_buffer : undefined,
    max_cloud: typeof result.max_cloud === 'number' ? result.max_cloud : null,
    mode,
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
