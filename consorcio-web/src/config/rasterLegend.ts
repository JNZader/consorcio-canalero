/**
 * Raster layer legend configuration.
 *
 * Color stops and rescale ranges are kept in sync with the backend
 * tile_service.py (DEFAULT_COLORMAPS / DEFAULT_RESCALE).
 * Hardcoded here to avoid an extra network request — update both
 * places when colormaps or ranges change.
 */

export interface CategoricalEntry {
  color: string;
  label: string;
}

export interface RangeEntry {
  label: string;
  min: number;
  max: number;
  color: string;
}

export interface RasterLegendInfo {
  /** CSS gradient color stops (5-7 stops matching the colormap) */
  colorStops: string[];
  /** Minimum value of the rescale range */
  min: number;
  /** Maximum value of the rescale range */
  max: number;
  /** Unit suffix shown after the value (empty string if unitless) */
  unit: string;
  /** Human-readable label for the legend */
  label: string;
  /** If true, render discrete color boxes with labels instead of a gradient */
  categorical?: boolean;
  /** Category entries (required when categorical is true) */
  categories?: CategoricalEntry[];
  /** Toggleable value ranges for continuous layers */
  ranges?: RangeEntry[];
}

export const LAYER_LEGEND_CONFIG: Record<string, RasterLegendInfo> = {
  terrain_class: {
    colorStops: ['#4CAF50', '#1E88E5', '#D32F2F', '#FF8F00'],
    min: 0,
    max: 3,
    unit: '',
    label: 'Clasificación de Terreno',
    categorical: true,
    categories: [
      { color: '#4CAF50', label: 'Sin Riesgo' },
      { color: '#1E88E5', label: 'Drenaje Natural' },
      { color: '#D32F2F', label: 'Riesgo Alto' },
      { color: '#FF8F00', label: 'Riesgo Medio' },
    ],
  },
  flood_risk: {
    colorStops: ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59', '#d73027'],
    min: 10,
    max: 90,
    unit: '',
    label: 'Riesgo de Inundación',
    ranges: [
      { label: 'Bajo', min: 0, max: 30, color: '#1a9850' },
      { label: 'Medio', min: 30, max: 55, color: '#fee08b' },
      { label: 'Alto', min: 55, max: 75, color: '#fc8d59' },
      { label: 'Crítico', min: 75, max: 100, color: '#d73027' },
    ],
  },
  drainage_need: {
    colorStops: ['#fff7ec', '#fee8c8', '#fdd49e', '#fdbb84', '#e34a33', '#b30000'],
    min: 20,
    max: 70,
    unit: '',
    label: 'Necesidad de Drenaje',
    ranges: [
      { label: 'Bajo', min: 0, max: 30, color: '#fff7ec' },
      { label: 'Medio', min: 30, max: 50, color: '#fdd49e' },
      { label: 'Alto', min: 50, max: 70, color: '#e34a33' },
      { label: 'Crítico', min: 70, max: 100, color: '#b30000' },
    ],
  },
  twi: {
    colorStops: ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
    min: 6,
    max: 19,
    unit: '',
    label: 'Índice Humedad (TWI)',
    ranges: [
      { label: 'Seco', min: 6, max: 9, color: '#f7fbff' },
      { label: 'Normal', min: 9, max: 12, color: '#6baed6' },
      { label: 'Húmedo', min: 12, max: 16, color: '#2171b5' },
      { label: 'Muy Húmedo', min: 16, max: 19, color: '#08306b' },
    ],
  },
  hand: {
    colorStops: ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'],
    min: 0,
    max: 4,
    unit: 'm',
    label: 'Altura sobre Drenaje (HAND)',
    ranges: [
      { label: 'Muy Bajo (<0.5m)', min: 0, max: 0.5, color: '#bd0026' },
      { label: 'Bajo (0.5-1m)', min: 0.5, max: 1.0, color: '#f03b20' },
      { label: 'Medio (1-2m)', min: 1.0, max: 2.0, color: '#fd8d3c' },
      { label: 'Alto (>2m)', min: 2.0, max: 4.0, color: '#ffffb2' },
    ],
  },
  slope: {
    colorStops: ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59', '#d73027'],
    min: 0,
    max: 1.5,
    unit: '°',
    label: 'Pendiente',
    ranges: [
      { label: 'Plano (<0.3°)', min: 0, max: 0.3, color: '#1a9850' },
      { label: 'Suave (0.3-0.7°)', min: 0.3, max: 0.7, color: '#fee08b' },
      { label: 'Moderado (>0.7°)', min: 0.7, max: 1.5, color: '#d73027' },
    ],
  },
  dem_raw: {
    colorStops: ['#333399', '#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c'],
    min: 100,
    max: 145,
    unit: 'm',
    label: 'Elevación (DEM)',
    ranges: [
      { label: 'Bajo (<110m)', min: 100, max: 110, color: '#333399' },
      { label: 'Medio (110-125m)', min: 110, max: 125, color: '#abdda4' },
      { label: 'Alto (125-145m)', min: 125, max: 145, color: '#d7191c' },
    ],
  },
  flow_acc: {
    colorStops: ['#ffffcc', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#0c2c84'],
    min: 1,
    max: 487848,
    unit: 'celdas',
    label: 'Acumulación de Flujo',
    ranges: [
      { label: 'Bajo', min: 1, max: 100, color: '#ffffcc' },
      { label: 'Medio', min: 100, max: 10000, color: '#7fcdbb' },
      { label: 'Alto', min: 10000, max: 487848, color: '#0c2c84' },
    ],
  },
  profile_curvature: {
    colorStops: ['#b2182b', '#ef8a62', '#fddbc7', '#f7f7f7', '#d1e5f0', '#67a9cf', '#2166ac'],
    min: -0.001,
    max: 0.001,
    unit: '',
    label: 'Curvatura',
    ranges: [
      { label: 'Cóncavo', min: -0.001, max: -0.0002, color: '#b2182b' },
      { label: 'Plano', min: -0.0002, max: 0.0002, color: '#f7f7f7' },
      { label: 'Convexo', min: 0.0002, max: 0.001, color: '#2166ac' },
    ],
  },
  tpi: {
    colorStops: ['#b2182b', '#ef8a62', '#fddbc7', '#f7f7f7', '#d1e5f0', '#67a9cf', '#2166ac'],
    min: -1.5,
    max: 1.5,
    unit: 'm',
    label: 'Posición Topográfica (TPI)',
    ranges: [
      { label: 'Valle', min: -1.5, max: -0.5, color: '#b2182b' },
      { label: 'Llano', min: -0.5, max: 0.5, color: '#f7f7f7' },
      { label: 'Cresta', min: 0.5, max: 1.5, color: '#2166ac' },
    ],
  },
};
