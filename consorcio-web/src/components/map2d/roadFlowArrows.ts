/**
 * Along-road flow arrows. The operator asked for chevrons of water direction
 * on the trace, sized in PIXELS so they survive overview zoom. The 40 m
 * geographic ticks of the first cut were invisible at the scale the map opens.
 */

import type { Feature, FeatureCollection, Point } from 'geojson';
import type maplibregl from 'maplibre-gl';

import { ROAD_FLOW_KINDS, type RoadFlowCrossingFeature } from '../../lib/api/roadFlow';

export const FLOW_ARROW_IMAGE_ID = 'road-flow-arrow';

export function alongRoadAzimuth(flowDeg: number, rumboDeg: number): number {
  const delta = ((flowDeg - rumboDeg) * Math.PI) / 180;
  if (Math.cos(delta) >= 0) return ((rumboDeg % 360) + 360) % 360;
  return (((rumboDeg + 180) % 360) + 360) % 360;
}

export interface RoadFlowArrowProperties {
  readonly id: string;
  readonly tramo_ref: string;
  readonly along_azimuth_deg: number;
  readonly direccion_flujo_deg?: number;
  readonly rumbo_camino_deg?: number;
}

export type RoadFlowArrowFeature = Feature<Point, RoadFlowArrowProperties>;
export type RoadFlowArrowCollection = FeatureCollection<Point, RoadFlowArrowProperties>;

/** Canvas triangle pointing NORTH. `icon-rotate` is the along-road azimuth. */
export function ensureFlowArrowImage(map: Pick<maplibregl.Map, 'hasImage' | 'addImage'>): void {
  if (map.hasImage(FLOW_ARROW_IMAGE_ID)) return;
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.beginPath();
  ctx.moveTo(size / 2, 4);
  ctx.lineTo(size - 6, size - 6);
  ctx.lineTo(6, size - 6);
  ctx.closePath();
  ctx.fillStyle = '#FF6D00';
  ctx.fill();
  ctx.lineWidth = 5;
  ctx.strokeStyle = '#111111';
  ctx.stroke();
  map.addImage(FLOW_ARROW_IMAGE_ID, ctx.getImageData(0, 0, size, size), { pixelRatio: 2 });
}

/**
 * Fallback when the run predates `flechas`: one pixel-arrow per stored
 * `conduccion` point. Better than a 40 m tick; still sparse until recompute.
 */
export function buildConduccionArrowCollection(
  crossings: FeatureCollection<Point> | null | undefined
): RoadFlowArrowCollection {
  const features: RoadFlowArrowFeature[] = [];
  for (const raw of crossings?.features ?? []) {
    const feature = raw as RoadFlowCrossingFeature;
    const p = feature.properties;
    if (p?.tipo !== ROAD_FLOW_KINDS.CONDUCCION) continue;
    const coords = feature.geometry?.coordinates;
    if (!coords || coords.length < 2) continue;
    const [lon, lat] = coords;
    const flow = p.direccion_flujo_deg;
    const rumbo = p.rumbo_camino_deg;
    if (
      !Number.isFinite(lon) ||
      !Number.isFinite(lat) ||
      flow === null ||
      rumbo === null ||
      !Number.isFinite(flow) ||
      !Number.isFinite(rumbo)
    ) {
      continue;
    }
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lon, lat] },
      properties: {
        id: p.id,
        tramo_ref: p.tramo_ref,
        along_azimuth_deg: alongRoadAzimuth(flow, rumbo),
        direccion_flujo_deg: flow,
        rumbo_camino_deg: rumbo,
      },
    });
  }
  return { type: 'FeatureCollection', features };
}

export function pickArrowCollection(
  flechas: FeatureCollection<Point> | null | undefined,
  crossings: FeatureCollection<Point> | null | undefined
): RoadFlowArrowCollection {
  if (flechas && flechas.features.length > 0) {
    return flechas as RoadFlowArrowCollection;
  }
  return buildConduccionArrowCollection(crossings);
}
