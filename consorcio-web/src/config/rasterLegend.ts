import { mapColorTokens } from '../lib/mapColorTokens';
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
    colorStops: [
      mapColorTokens.h4CAF50,
      mapColorTokens.h1E88E5,
      mapColorTokens.hD32F2F,
      mapColorTokens.hFF8F00,
    ],
    min: 0,
    max: 3,
    unit: '',
    label: 'Clasificación de Terreno',
    categorical: true,
    categories: [
      { color: mapColorTokens.h4CAF50, label: 'Sin Riesgo' },
      { color: mapColorTokens.h1E88E5, label: 'Drenaje Natural' },
      { color: mapColorTokens.hD32F2F, label: 'Riesgo Alto' },
      { color: mapColorTokens.hFF8F00, label: 'Riesgo Medio' },
    ],
  },
  flood_risk: {
    // ColorBrewer Oranges 4, colorblind-safe (not red/green).
    colorStops: [
      mapColorTokens.hfeedde,
      mapColorTokens.hfdbe85,
      mapColorTokens.hfd8d3c,
      mapColorTokens.he6550d,
      mapColorTokens.ha63603,
    ],
    min: 10,
    max: 90,
    unit: 'índice 0–100',
    label: 'Riesgo de Inundación',
    ranges: [
      { label: 'Bajo', min: 0, max: 30, color: mapColorTokens.hfeedde },
      { label: 'Medio', min: 30, max: 55, color: mapColorTokens.hfdbe85 },
      { label: 'Alto', min: 55, max: 75, color: mapColorTokens.hfd8d3c },
      { label: 'Crítico', min: 75, max: 100, color: mapColorTokens.ha63603 },
    ],
  },
  drainage_need: {
    colorStops: [
      mapColorTokens.hf1eef6,
      mapColorTokens.hbdc9e1,
      mapColorTokens.h74a9cf,
      mapColorTokens.h2b8cbe,
      mapColorTokens.h045a8d,
    ],
    min: 20,
    max: 70,
    unit: 'índice 0–100',
    label: 'Necesidad de Drenaje',
    ranges: [
      { label: 'Bajo', min: 0, max: 30, color: mapColorTokens.hf1eef6 },
      { label: 'Medio', min: 30, max: 50, color: mapColorTokens.hbdc9e1 },
      { label: 'Alto', min: 50, max: 70, color: mapColorTokens.h2b8cbe },
      { label: 'Crítico', min: 70, max: 100, color: mapColorTokens.h045a8d },
    ],
  },
  twi: {
    colorStops: [
      mapColorTokens.hf7fbff,
      mapColorTokens.hc6dbef,
      mapColorTokens.h6baed6,
      mapColorTokens.h2171b5,
      mapColorTokens.h08306b,
    ],
    min: 6,
    max: 19,
    unit: '',
    label: 'Índice Humedad (TWI)',
    ranges: [
      { label: 'Seco', min: 6, max: 9, color: mapColorTokens.hf7fbff },
      { label: 'Normal', min: 9, max: 12, color: mapColorTokens.h6baed6 },
      { label: 'Húmedo', min: 12, max: 16, color: mapColorTokens.h2171b5 },
      { label: 'Muy Húmedo', min: 16, max: 19, color: mapColorTokens.h08306b },
    ],
  },
  hand: {
    colorStops: [
      mapColorTokens.hffffb2,
      mapColorTokens.hfecc5c,
      mapColorTokens.hfd8d3c,
      mapColorTokens.hf03b20,
      mapColorTokens.hbd0026,
    ],
    min: 0,
    max: 4,
    unit: 'm',
    label: 'Altura sobre Drenaje (HAND)',
    ranges: [
      { label: 'Muy Bajo (<0.5m)', min: 0, max: 0.5, color: mapColorTokens.hbd0026 },
      { label: 'Bajo (0.5-1m)', min: 0.5, max: 1.0, color: mapColorTokens.hf03b20 },
      { label: 'Medio (1-2m)', min: 1.0, max: 2.0, color: mapColorTokens.hfd8d3c },
      { label: 'Alto (>2m)', min: 2.0, max: 4.0, color: mapColorTokens.hffffb2 },
    ],
  },
  slope: {
    colorStops: [
      mapColorTokens.hffffd4,
      mapColorTokens.hfee391,
      mapColorTokens.hfec44f,
      mapColorTokens.hfe9929,
      mapColorTokens.hd95f0e,
      mapColorTokens.h993404,
    ],
    min: 0,
    max: 17.5,
    unit: 'm/1000m',
    label: 'Pendiente',
    ranges: [
      { label: 'Muy baja zona I (<0.5 m/1000m)', min: 0, max: 0.5, color: mapColorTokens.hffffd4 },
      {
        label: 'Muy baja zona II (0.5-2.1 m/1000m)',
        min: 0.5,
        max: 2.1,
        color: mapColorTokens.hfee391,
      },
      { label: 'Baja zona (2.1-4.2 m/1000m)', min: 2.1, max: 4.2, color: mapColorTokens.hfec44f },
      { label: 'Suave zona (4.2-6.9 m/1000m)', min: 4.2, max: 6.9, color: mapColorTokens.hfe9929 },
      {
        label: 'Moderada zona (6.9-15.3 m/1000m)',
        min: 6.9,
        max: 15.3,
        color: mapColorTokens.hd95f0e,
      },
      {
        label: 'Alta puntual (>15.3 m/1000m)',
        min: 15.3,
        max: 1000,
        color: mapColorTokens.h993404,
      },
    ],
  },
  dem_raw: {
    colorStops: [
      mapColorTokens.h333399,
      mapColorTokens.h2b83ba,
      mapColorTokens.habdda4,
      mapColorTokens.hffffbf,
      mapColorTokens.hfdae61,
      mapColorTokens.hd7191c,
    ],
    min: 100,
    max: 145,
    unit: 'm',
    label: 'Elevación (DEM)',
    ranges: [
      { label: '100-105m', min: 100, max: 105, color: mapColorTokens.h08306b },
      { label: '105-110m', min: 105, max: 110, color: mapColorTokens.h2171b5 },
      { label: '110-115m', min: 110, max: 115, color: mapColorTokens.h6baed6 },
      { label: '115-120m', min: 115, max: 120, color: mapColorTokens.ha1d99b },
      { label: '120-125m', min: 120, max: 125, color: mapColorTokens.hffffbf },
      { label: '125-130m', min: 125, max: 130, color: mapColorTokens.hfdae61 },
      { label: '130-135m', min: 130, max: 135, color: mapColorTokens.hf46d43 },
      { label: '135-145m', min: 135, max: 145, color: mapColorTokens.ha50026 },
    ],
  },
  precip_normal: {
    colorStops: [
      mapColorTokens.hffffcc,
      mapColorTokens.hc7e9b4,
      mapColorTokens.h7fcdbb,
      mapColorTokens.h41b6c4,
      mapColorTokens.h1d91c0,
      mapColorTokens.h0c2c84,
    ],
    min: 0,
    max: 1800,
    unit: 'mm',
    label: 'CHIRPS 1991-2020 normal',
  },
  flow_acc: {
    colorStops: [
      mapColorTokens.hffffcc,
      mapColorTokens.hc7e9b4,
      mapColorTokens.h7fcdbb,
      mapColorTokens.h41b6c4,
      mapColorTokens.h1d91c0,
      mapColorTokens.h0c2c84,
    ],
    min: 1,
    max: 487848,
    unit: 'celdas',
    label: 'Acumulación de Flujo',
    ranges: [
      { label: 'Mínimo (1 celda)', min: 1, max: 1.5, color: mapColorTokens.hffffcc },
      { label: 'Muy bajo (2-6)', min: 1.5, max: 6, color: mapColorTokens.hd9f0a3 },
      { label: 'Bajo (6-53)', min: 6, max: 53, color: mapColorTokens.haddd8e },
      { label: 'Moderado (53-210)', min: 53, max: 210, color: mapColorTokens.h78c679 },
      { label: 'Alto (210-6.525)', min: 210, max: 6525.22, color: mapColorTokens.h41b6c4 },
      { label: 'Muy alto (>6.525)', min: 6525.22, max: 487848, color: mapColorTokens.h0c2c84 },
    ],
  },
  profile_curvature: {
    colorStops: [
      mapColorTokens.hb2182b,
      mapColorTokens.hef8a62,
      mapColorTokens.hfddbc7,
      mapColorTokens.hf7f7f7,
      mapColorTokens.hd1e5f0,
      mapColorTokens.h67a9cf,
      mapColorTokens.h2166ac,
    ],
    min: -0.001,
    max: 0.001,
    unit: '',
    label: 'Curvatura',
    ranges: [
      { label: 'Cóncavo', min: -0.001, max: -0.0002, color: mapColorTokens.hb2182b },
      { label: 'Plano', min: -0.0002, max: 0.0002, color: mapColorTokens.hf7f7f7 },
      { label: 'Convexo', min: 0.0002, max: 0.001, color: mapColorTokens.h2166ac },
    ],
  },
  tpi: {
    colorStops: [
      mapColorTokens.hb2182b,
      mapColorTokens.hef8a62,
      mapColorTokens.hfddbc7,
      mapColorTokens.hf7f7f7,
      mapColorTokens.hd1e5f0,
      mapColorTokens.h67a9cf,
      mapColorTokens.h2166ac,
    ],
    min: -1.5,
    max: 1.5,
    unit: 'm',
    label: 'Posición Topográfica (TPI)',
    ranges: [
      { label: 'Valle', min: -1.5, max: -0.5, color: mapColorTokens.hb2182b },
      { label: 'Llano', min: -0.5, max: 0.5, color: mapColorTokens.hf7f7f7 },
      { label: 'Cresta', min: 0.5, max: 1.5, color: mapColorTokens.h2166ac },
    ],
  },
};
