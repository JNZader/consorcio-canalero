/**
 * Map-wide label size scale (roads + staff POI titles).
 *
 * Default `1` keeps the hardcoded interpolate stops. The slider in Capas
 * multiplies those stops; persist lives on `mapLayerSyncStore.labelSizeScale`.
 */
import type { ExpressionSpecification } from 'maplibre-gl';

import { ALONG_LINE_LABEL_TEXT_SIZE } from './alongLineLabel';
import { buildWaterwayLayerConfigs, SOURCE_IDS } from './map2dConfig';
import { PUNTOS_INTERES_LABEL_LAYER_ID, PUNTO_INTERES_LABEL_TEXT_SIZE } from './puntosInteresLayers';
import { ROAD_LABEL_TEXT_SIZE } from './roadLabelLayer';

export const DEFAULT_LABEL_SIZE_SCALE = 1;
export const LABEL_SIZE_SCALE_MIN = 0.75;
export const LABEL_SIZE_SCALE_MAX = 2.5;

export function clampLabelSizeScale(value: number): number {
  if (!Number.isFinite(value)) return DEFAULT_LABEL_SIZE_SCALE;
  return Math.min(LABEL_SIZE_SCALE_MAX, Math.max(LABEL_SIZE_SCALE_MIN, value));
}

/** Multiply numeric size stops of an `interpolate` on zoom. */
export function scaleTextSizeExpression(
  base: ExpressionSpecification,
  scale: number
): ExpressionSpecification {
  const clamped = clampLabelSizeScale(scale);
  if (!Array.isArray(base) || base[0] !== 'interpolate') return base;
  const next = [...base] as unknown[];
  for (let i = 4; i < next.length; i += 2) {
    const size = next[i];
    if (typeof size === 'number') {
      next[i] = Math.round(size * clamped * 10) / 10;
    }
  }
  return next as ExpressionSpecification;
}

export interface MapLabelSizeApi {
  getLayer: (id: string) => unknown;
  setLayoutProperty: (id: string, prop: string, value: unknown) => void;
}

const MAP2D_TEXT_LAYERS: ReadonlyArray<{ id: string; base: ExpressionSpecification }> = [
  { id: `${SOURCE_IDS.ROADS}-label`, base: ROAD_LABEL_TEXT_SIZE },
  { id: PUNTOS_INTERES_LABEL_LAYER_ID, base: PUNTO_INTERES_LABEL_TEXT_SIZE },
  { id: `${SOURCE_IDS.CANALES_RELEVADOS}-label`, base: ALONG_LINE_LABEL_TEXT_SIZE },
  { id: `${SOURCE_IDS.CANALES_PROPUESTOS}-label`, base: ALONG_LINE_LABEL_TEXT_SIZE },
  ...buildWaterwayLayerConfigs([]).map((cfg) => ({
    id: `${cfg.id}-label`,
    base: ALONG_LINE_LABEL_TEXT_SIZE,
  })),
];

export function applyMapLabelSize(map: MapLabelSizeApi, scale: number): void {
  if (typeof map.getLayer !== 'function' || typeof map.setLayoutProperty !== 'function') {
    return;
  }
  const clamped = clampLabelSizeScale(scale);
  for (const layer of MAP2D_TEXT_LAYERS) {
    if (!map.getLayer(layer.id)) continue;
    map.setLayoutProperty(layer.id, 'text-size', scaleTextSizeExpression(layer.base, clamped));
  }
}
