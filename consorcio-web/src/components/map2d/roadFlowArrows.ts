/**
 * Along-road arrows for `tipo=conduccion` points (flujo-caminos, cuneta slice).
 *
 * The backend stores a POINT plus two azimuths. The map needs a short
 * LineString in the along-road direction of the D8 pointer — not the raw D8
 * azimuth, which is quantized to 45° and would paint off the trace.
 */

import type { Feature, FeatureCollection, Geometry, Point } from 'geojson';

import { ROAD_FLOW_KINDS, type RoadFlowCrossingFeature } from '../../lib/api/roadFlow';

/** Arrow shaft length. Half a GLO-30 cell — long enough to read, short enough
 *  not to look like a canal. */
export const ROAD_FLOW_ARROW_LENGTH_M = 40;

const EARTH_RADIUS_M = 6_371_000;

export function alongRoadAzimuth(flowDeg: number, rumboDeg: number): number {
  const delta = ((flowDeg - rumboDeg) * Math.PI) / 180;
  if (Math.cos(delta) >= 0) return ((rumboDeg % 360) + 360) % 360;
  return (((rumboDeg + 180) % 360) + 360) % 360;
}

export function destinationPoint(
  lon: number,
  lat: number,
  azimuthDeg: number,
  meters: number
): [number, number] {
  const br = (azimuthDeg * Math.PI) / 180;
  const lat1 = (lat * Math.PI) / 180;
  const lon1 = (lon * Math.PI) / 180;
  const ang = meters / EARTH_RADIUS_M;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(ang) + Math.cos(lat1) * Math.sin(ang) * Math.cos(br)
  );
  const lon2 =
    lon1 +
    Math.atan2(
      Math.sin(br) * Math.sin(ang) * Math.cos(lat1),
      Math.cos(ang) - Math.sin(lat1) * Math.sin(lat2)
    );
  return [(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI];
}

export interface RoadFlowArrowProperties {
  readonly id: string;
  readonly tipo: typeof ROAD_FLOW_KINDS.CONDUCCION;
  readonly tramo_ref: string;
  readonly canal_ref: string | null;
  readonly direccion_flujo_deg: number;
  readonly rumbo_camino_deg: number;
  readonly along_azimuth_deg: number;
  readonly nota: string | null;
}

export type RoadFlowArrowFeature = Feature<Geometry, RoadFlowArrowProperties>;
export type RoadFlowArrowCollection = FeatureCollection<Geometry, RoadFlowArrowProperties>;

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
    const along = alongRoadAzimuth(flow, rumbo);
    const tip = destinationPoint(lon, lat, along, ROAD_FLOW_ARROW_LENGTH_M);
    const properties: RoadFlowArrowProperties = {
      id: p.id,
      tipo: ROAD_FLOW_KINDS.CONDUCCION,
      tramo_ref: p.tramo_ref,
      canal_ref: p.canal_ref,
      direccion_flujo_deg: flow,
      rumbo_camino_deg: rumbo,
      along_azimuth_deg: along,
      nota: p.nota,
    };
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: [[lon, lat], tip] },
      properties,
    });
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: tip },
      properties: { ...properties, id: `${p.id}-tip` },
    });
  }
  return { type: 'FeatureCollection', features };
}
