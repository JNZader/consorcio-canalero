import type { Feature, FeatureCollection, Geometry } from 'geojson';
import type maplibregl from 'maplibre-gl';

/**
 * Build a MapLibre filter expression for the `catastro` layer that shows only
 * parcels whose geometry intersects the selected basin.
 *
 * The source geometry MUST be present on the feature (`feature.geometry`) so the
 * filter can use the client-side `within` expression. The backend currently serves
 * parcel polygons as GeoJSON; the vector tile version would need a per-basin
 * server clip, which is out of scope for v1.
 *
 * @returns A MapLibre filter array. Returns `null` when "all basins" is selected
 *          or the input has no geometry, which callers should interpret as
 *          "remove any existing filter".
 */
export function buildBasinCatastroFilter(
  basin: Feature<Geometry> | null | undefined
): maplibregl.FilterSpecification | null {
  if (!basin || !basin.geometry) return null;

  return [
    'within',
    {
      type: 'Feature',
      geometry: basin.geometry,
      properties: {},
    } as Feature<Geometry>,
  ] as unknown as maplibregl.FilterSpecification;
}

/**
 * Find a basin feature by its `id` property in a FeatureCollection.
 */
export function findBasinById(
  basins: FeatureCollection | null | undefined,
  id: string | null | undefined
): Feature<Geometry> | undefined {
  if (!basins || !id) return undefined;
  return basins.features.find((f) => String(f.properties?.id ?? f.id) === id);
}

/**
 * Build a GeoJSON FeatureCollection containing exactly one basin feature.
 * Useful for `within` filter inputs and bbox helpers.
 */
export function basinToFeatureCollection(basin: Feature<Geometry>): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [basin],
  };
}
