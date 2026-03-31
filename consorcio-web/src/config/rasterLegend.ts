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
    max: 17.5,
    unit: 'm/1000m',
    label: 'Pendiente',
    ranges: [
      { label: 'Muy baja zona I (<0.5 m/1000m)', min: 0, max: 0.5, color: '#0b7d3b' },
      { label: 'Muy baja zona II (0.5-2.1 m/1000m)', min: 0.5, max: 2.1, color: '#1a9850' },
      { label: 'Baja zona (2.1-4.2 m/1000m)', min: 2.1, max: 4.2, color: '#91cf60' },
      { label: 'Suave zona (4.2-6.9 m/1000m)', min: 4.2, max: 6.9, color: '#d9ef8b' },
      { label: 'Moderada zona (6.9-15.3 m/1000m)', min: 6.9, max: 15.3, color: '#fc8d59' },
      { label: 'Alta puntual (>15.3 m/1000m)', min: 15.3, max: 1000, color: '#d73027' },
    ],
  },
  dem_raw: {
    colorStops: ['#333399', '#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c'],
    min: 100,
    max: 145,
    unit: 'm',
    label: 'Elevación (DEM)',
    ranges: [
      { label: '100-105m', min: 100, max: 105, color: '#08306b' },
      { label: '105-110m', min: 105, max: 110, color: '#2171b5' },
      { label: '110-115m', min: 110, max: 115, color: '#6baed6' },
      { label: '115-120m', min: 115, max: 120, color: '#a1d99b' },
      { label: '120-125m', min: 120, max: 125, color: '#ffffbf' },
      { label: '125-130m', min: 125, max: 130, color: '#fdae61' },
      { label: '130-135m', min: 130, max: 135, color: '#f46d43' },
      { label: '135-145m', min: 135, max: 145, color: '#a50026' },
    ],
  },
  flow_acc: {
    colorStops: ['#ffffcc', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#0c2c84'],
    min: 1,
    max: 487848,
    unit: 'celdas',
    label: 'Acumulación de Flujo',
    ranges: [
      { label: 'Mínimo (1 celda)', min: 1, max: 1.5, color: '#ffffcc' },
      { label: 'Muy bajo (2-6)', min: 1.5, max: 6, color: '#d9f0a3' },
      { label: 'Bajo (6-53)', min: 6, max: 53, color: '#addd8e' },
      { label: 'Moderado (53-210)', min: 53, max: 210, color: '#78c679' },
      { label: 'Alto (210-6.525)', min: 210, max: 6525.22, color: '#41b6c4' },
      { label: 'Muy alto (>6.525)', min: 6525.22, max: 487848, color: '#0c2c84' },
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
