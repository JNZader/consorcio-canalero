/**
 * B3 precomputes parcel/basin intersections and supplies the identifier
 * property it used. This presentational helper only translates that evidence
 * into a MapLibre membership expression; MapLibre cannot calculate polygon
 * intersections in a layer filter. A null filter restores all source features.
 */
export const HAZARD_BASIN_FILTER_ALL = 'all' as const;

export interface HazardBasinMembership {
  readonly featureIdProperty: string;
  readonly intersectingFeatureIds: readonly (string | number)[];
}

export type HazardBasinFilter =
  | ['in', ['get', string], ['literal', Array<string | number>]]
  | null;

export function buildHazardBasinFilter(
  membership: HazardBasinMembership | typeof HAZARD_BASIN_FILTER_ALL | null | undefined
): HazardBasinFilter {
  if (!membership || membership === HAZARD_BASIN_FILTER_ALL) return null;

  return [
    'in',
    ['get', membership.featureIdProperty],
    ['literal', [...membership.intersectingFeatureIds]],
  ];
}
