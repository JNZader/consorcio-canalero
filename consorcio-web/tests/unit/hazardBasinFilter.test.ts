import { describe, expect, it } from 'vitest';

import {
  buildHazardBasinFilter,
  HAZARD_BASIN_FILTER_ALL,
} from '../../src/components/map2d/hazardBasinFilter';

describe('buildHazardBasinFilter', () => {
  it('returns null to restore all parcels when no membership evidence or all scope is selected', () => {
    expect(buildHazardBasinFilter(null)).toBeNull();
    expect(buildHazardBasinFilter(HAZARD_BASIN_FILTER_ALL)).toBeNull();
  });

  it('builds a membership filter from the caller-provided parcel id property', () => {
    expect(
      buildHazardBasinFilter({
        featureIdProperty: 'parcel_ref',
        intersectingFeatureIds: ['19-01-001', '19-01-002'],
      })
    ).toEqual([
      'in',
      ['get', 'parcel_ref'],
      ['literal', ['19-01-001', '19-01-002']],
    ]);
  });

  it('matches no parcels when precomputed intersection evidence is empty', () => {
    expect(
      buildHazardBasinFilter({
        featureIdProperty: 'source_id',
        intersectingFeatureIds: [],
      })
    ).toEqual(['in', ['get', 'source_id'], ['literal', []]]);
  });
});
