import type { FeatureCollection } from 'geojson';

import type { HazardBasinOption } from './hazardControls.types';

/**
 * Adapts the `/api/v2/geo/basins` FeatureCollection into selector options.
 * The API emits the basin UUID as `properties.id` (never `basin_id` — that key
 * belongs to the separate basin-membership response) and the name as
 * `properties.nombre`. Features without a non-empty string id are dropped; the
 * geometry rides along so a selected basin can drive a bounded map zoom.
 */
export function buildHazardBasinOptions(
  basins: FeatureCollection | null | undefined
): HazardBasinOption[] {
  return (basins?.features ?? []).flatMap((feature) => {
    const basinId = feature.properties?.id;
    if (typeof basinId !== 'string' || basinId.trim() === '') return [];

    const id = basinId.trim();
    const nombre = feature.properties?.nombre;
    const label = typeof nombre === 'string' && nombre.trim() !== '' ? nombre : `Cuenca ${id}`;
    return [{ id, label, geometry: feature.geometry ?? null }];
  });
}
