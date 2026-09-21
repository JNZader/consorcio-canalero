/**
 * Map-wide line-width scale (roads, canales, waterways, outlines).
 * Does not touch invisible hit layers (`*-hit`).
 */
import { buildWaterwayLayerConfigs, SOURCE_IDS } from './map2dConfig';

export const DEFAULT_LINE_WIDTH_SCALE = 1;
export const LINE_WIDTH_SCALE_MIN = 0.75;
export const LINE_WIDTH_SCALE_MAX = 2.5;

export function clampLineWidthScale(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_LINE_WIDTH_SCALE;
  return Math.min(LINE_WIDTH_SCALE_MAX, Math.max(LINE_WIDTH_SCALE_MIN, value));
}

/** Hardcoded paints in mapLayerEffectHelpers / canalesLayers. */
export const MAP_LINE_WIDTH_LAYERS: ReadonlyArray<{ id: string; base: number }> = [
  { id: `${SOURCE_IDS.ROADS}-line`, base: 2 },
  { id: `${SOURCE_IDS.CANALES_RELEVADOS}-line`, base: 3 },
  { id: `${SOURCE_IDS.CANALES_PROPUESTOS}-line`, base: 2.5 },
  { id: `${SOURCE_IDS.SOIL}-line`, base: 1.2 },
  { id: `${SOURCE_IDS.CATASTRO}-line`, base: 1.5 },
  { id: `${SOURCE_IDS.BASINS}-line`, base: 1.5 },
  { id: `${SOURCE_IDS.APPROVED_ZONES}-line`, base: 3 },
  { id: `${SOURCE_IDS.ZONA}-line`, base: 3 },
  ...buildWaterwayLayerConfigs([]).map((cfg) => ({ id: `${cfg.id}-line`, base: 3 })),
];

export interface MapLineWidthApi {
  getLayer: (id: string) => unknown;
  setPaintProperty: (id: string, prop: string, value: unknown) => void;
}

export function applyMapLineWidth(map: MapLineWidthApi, scale: number): void {
  if (typeof map.getLayer !== 'function' || typeof map.setPaintProperty !== 'function') {
    return;
  }
  const clamped = clampLineWidthScale(scale);
  for (const layer of MAP_LINE_WIDTH_LAYERS) {
    if (!map.getLayer(layer.id)) continue;
    map.setPaintProperty(layer.id, 'line-width', Math.round(layer.base * clamped * 10) / 10);
  }
}
