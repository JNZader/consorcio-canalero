import area from '@turf/area';
import length from '@turf/length';
import type { Feature, LineString, Polygon } from 'geojson';

import { formatArea, formatDistance } from './measurementFormat';
import type { MeasurementMode } from './useMeasurement';

/** Meters of the line the user drew. A nearby canal or road is not consulted. */
export function drawnLineMeters(line: LineString): number {
  return length({ type: 'Feature', geometry: line, properties: {} }, { units: 'meters' });
}

export function liveMeasurementLabel(
  mode: MeasurementMode,
  features: readonly Feature[]
): string | null {
  if (mode === 'measuring-distance') {
    const line = features.find((feature) => feature.geometry.type === 'LineString') as
      | Feature<LineString>
      | undefined;
    if (!line || line.geometry.coordinates.length < 2) return null;
    return formatDistance(drawnLineMeters(line.geometry));
  }
  if (mode === 'measuring-area') {
    const polygon = features.find((feature) => feature.geometry.type === 'Polygon') as
      | Feature<Polygon>
      | undefined;
    const ring = polygon?.geometry.coordinates[0];
    if (!ring || ring.length < 4) return null;
    return formatArea(area(polygon));
  }
  return null;
}
