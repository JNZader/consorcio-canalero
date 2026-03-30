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
  },
  drainage_need: {
    colorStops: ['#fff7ec', '#fee8c8', '#fdd49e', '#fdbb84', '#e34a33', '#b30000'],
    min: 20,
    max: 70,
    unit: '',
    label: 'Necesidad de Drenaje',
  },
  twi: {
    colorStops: ['#f7fbff', '#c6dbef', '#6baed6', '#2171b5', '#08306b'],
    min: 6,
    max: 19,
    unit: '',
    label: 'Índice Humedad (TWI)',
  },
  hand: {
    colorStops: ['#ffffb2', '#fecc5c', '#fd8d3c', '#f03b20', '#bd0026'],
    min: 0,
    max: 4,
    unit: 'm',
    label: 'Altura sobre Drenaje (HAND)',
  },
  slope: {
    colorStops: ['#1a9850', '#91cf60', '#d9ef8b', '#fee08b', '#fc8d59', '#d73027'],
    min: 0,
    max: 1.5,
    unit: '°',
    label: 'Pendiente',
  },
  dem_raw: {
    colorStops: ['#333399', '#2b83ba', '#abdda4', '#ffffbf', '#fdae61', '#d7191c'],
    min: 100,
    max: 145,
    unit: 'm',
    label: 'Elevación (DEM)',
  },
  flow_acc: {
    colorStops: ['#ffffcc', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#0c2c84'],
    min: 1,
    max: 487848,
    unit: 'celdas',
    label: 'Acumulación de Flujo',
  },
  profile_curvature: {
    colorStops: ['#b2182b', '#ef8a62', '#fddbc7', '#f7f7f7', '#d1e5f0', '#67a9cf', '#2166ac'],
    min: -0.001,
    max: 0.001,
    unit: '',
    label: 'Curvatura',
  },
  tpi: {
    colorStops: ['#b2182b', '#ef8a62', '#fddbc7', '#f7f7f7', '#d1e5f0', '#67a9cf', '#2166ac'],
    min: -1.5,
    max: 1.5,
    unit: 'm',
    label: 'Posición Topográfica (TPI)',
  },
};
