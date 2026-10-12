import type { Feature, LineString, Polygon } from 'geojson';
import area from '@turf/area';
import length from '@turf/length';

import { formatArea, formatDistance } from './measurementFormat';
import type { MeasurementMode } from './useMeasurement';

export function liveMeasurementLabel(
  mode: MeasurementMode,
  features: readonly Feature[],
): string | null {
  if (mode === 'measuring-distance') {
    const line = features.find((feature) => feature.geometry.type === 'LineString') as
      | Feature<LineString>
      | undefined;
    if (!line || line.geometry.coordinates.length < 2) return null;
    return formatDistance(length(line, { units: 'meters' }));
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
