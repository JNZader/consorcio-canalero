import { describe, expect, it } from 'vitest';

import { mergeHazardCanonical, parseMapaRouteSearch } from '../../src/lib/mapaSearch';

describe('parseMapaRouteSearch', () => {
  it('keeps camera, permalink, and report pin keys next to hazard', () => {
    expect(
      parseMapaRouteSearch({
        hazard: '1',
        basin: 'basin-a',
        lat: '-32.4',
        lng: '-62.7',
        zoom: '12.5',
        preset: 'agua',
        l: 'roads',
        r: 'flood_risk',
        report: '1',
        junk: 'drop',
      })
    ).toEqual({
      hazard: '1',
      basin: 'basin-a',
      lat: '-32.4',
      lng: '-62.7',
      zoom: '12.5',
      preset: 'agua',
      l: 'roads',
      r: 'flood_risk',
      report: '1',
    });
  });

  it('does not invent a report pin from camera-only permalinks', () => {
    expect(parseMapaRouteSearch({ lat: '-32.4', lng: '-62.7', zoom: '11' })).toEqual({
      lat: '-32.4',
      lng: '-62.7',
      zoom: '11',
    });
  });
});

describe('mergeHazardCanonical', () => {
  it('replaces hazard keys without wiping camera permalink params', () => {
    expect(
      mergeHazardCanonical(
        { lat: '-32.4', lng: '-62.7', zoom: '12', preset: 'agua', hazard: '1', basin: 'old' },
        { hazard: '1' }
      )
    ).toEqual({ lat: '-32.4', lng: '-62.7', zoom: '12', preset: 'agua', hazard: '1' });
  });
});
