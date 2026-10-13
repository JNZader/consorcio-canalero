import type { LineLayerSpecification } from 'maplibre-gl';
import { mapColorTokens } from '../../lib/mapColorTokens';

export const LINE_CASING_OPACITY = 0.6;
export const LINE_CASING_EXTRA_WIDTH = 2;
export const LINE_CASING_COLOR_LIGHT = mapColorTokens.hffffff;
export const LINE_CASING_COLOR_DARK = mapColorTokens.h111111;

export function casingLayerId(lineLayerId: string): string {
  return `${lineLayerId}-casing`;
}

export function parseDashArray(dashArray: string | undefined): number[] | undefined {
  if (!dashArray) return undefined;
  const parts = dashArray
    .split(',')
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isFinite(value) && value >= 0);
  return parts.length >= 2 ? parts : undefined;
}

/**
 * CART-05: a wider, semi-opaque halo under thematic lines so they stay
 * readable on OSM and satellite (contrast ≥ 3:1).
 */
export function buildLineCasingLayer(input: {
  lineLayerId: string;
  source: string;
  width: number;
  dashArray?: string;
  darkHalo?: boolean;
}): LineLayerSpecification {
  const dash = parseDashArray(input.dashArray);
  return {
    id: casingLayerId(input.lineLayerId),
    type: 'line',
    source: input.source,
    layout: {
      'line-cap': 'round',
      'line-join': 'round',
    },
    paint: {
      'line-color': input.darkHalo ? LINE_CASING_COLOR_DARK : LINE_CASING_COLOR_LIGHT,
      'line-width': input.width + LINE_CASING_EXTRA_WIDTH,
      'line-opacity': LINE_CASING_OPACITY,
      ...(dash ? { 'line-dasharray': dash } : {}),
    },
  };
}

export function shouldAddCasing(
  map: { getLayer: (id: string) => unknown },
  lineLayerId: string
): boolean {
  return !map.getLayer(casingLayerId(lineLayerId));
}

export function ensureLineCasing(
  map: {
    getLayer: (id: string) => unknown;
    addLayer: (layer: LineLayerSpecification, before?: string) => void;
  },
  input: {
    lineLayerId: string;
    source: string;
    width: number;
    dashArray?: string;
    darkHalo?: boolean;
  }
): void {
  if (!map.getLayer(input.lineLayerId)) return;
  if (!shouldAddCasing(map, input.lineLayerId)) return;
  map.addLayer(buildLineCasingLayer(input), input.lineLayerId);
}
