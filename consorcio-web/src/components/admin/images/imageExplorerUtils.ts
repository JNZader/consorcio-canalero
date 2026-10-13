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

export type ImageSensor =
  | 'sentinel2'
  | 'sentinel1'
  | 'landsat9'
  | 'landsat8'
  | 'landsat7'
  | 'landsat5';

const IMAGE_SENSORS: ReadonlySet<string> = new Set([
  'sentinel2',
  'sentinel1',
  'landsat9',
  'landsat8',
  'landsat7',
  'landsat5',
]);

export function isImageSensor(value: string): value is ImageSensor {
  return IMAGE_SENSORS.has(value);
}

export function sensorLabel(sensor: ImageSensor): SatelliteSensorLabel {
  const labels: Record<ImageSensor, SatelliteSensorLabel> = {
    sentinel2: 'Sentinel-2',
    sentinel1: 'Sentinel-1',
    landsat9: 'Landsat 9',
    landsat8: 'Landsat 8',
    landsat7: 'Landsat 7',
    landsat5: 'Landsat 5',
  };
  return labels[sensor];
}

export function isOpticalSensor(sensor: ImageSensor): boolean {
  return sensor !== 'sentinel1';
}

/** QGIS-style NIR-R-G. Stored shortlist `rgb` is the old default — ignore it. */
export function explorerSceneVisualization(sensor: string, visualization?: string | null): string {
  if (sensor === 'sentinel1') return visualization || 'vv_flood';
  if (!visualization || visualization === 'rgb') return 'falso_color';
  return visualization;
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

/** Backend fills L7 SLC-off from `ordered_dates[1:6]` — at most 5 neighbors. */
export const L7_GAPFILL_MAX_NEIGHBORS = 5;

export function l7GapfillNeighborCount(result: ImageResultLike | null | undefined): number {
  if (result?.images_count != null && Number.isFinite(result.images_count)) {
    return Math.min(L7_GAPFILL_MAX_NEIGHBORS, Math.max(0, result.images_count - 1));
  }
  return L7_GAPFILL_MAX_NEIGHBORS;
}

export function l7GapfillHelp(result: ImageResultLike | null | undefined): string {
  const n = l7GapfillNeighborCount(result);
  return `Landsat 7 desde 2003 trae franjas SLC-off. El relleno usa hasta ${n} fechas vecinas (sin interpolar huecos). Si queda feo, cambiate a escena individual o a Landsat 8.`;
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
      label: v.description || v.id || `Visualización ${index + 1}`,
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
