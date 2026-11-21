import { describe, expect, it } from 'vitest';

import { mergeHazardCanonical, parseMapaRouteSearch } from '../../src/lib/mapaSearch';

describe('parseMapaRouteSearch', () => {
  it('keeps camera, permalink, view, and report pin keys next to hazard', () => {
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
        perfil: 'canal-ne-sin-intervencion',
        view: '3d',
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
      perfil: 'canal-ne-sin-intervencion',
      view: '3d',
      report: '1',
    });
  });

  it('drops unsupported view values and keeps view=2d', () => {
    expect(parseMapaRouteSearch({ view: '2d' })).toEqual({ view: '2d' });
    expect(parseMapaRouteSearch({ view: 'orbit' })).toEqual({});
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
  it('replaces hazard keys without wiping camera permalink params or view', () => {
    expect(
      mergeHazardCanonical(
        {
          lat: '-32.4',
          lng: '-62.7',
          zoom: '12',
          preset: 'agua',
          view: '3d',
          hazard: '1',
          basin: 'old',
        },
        { hazard: '1' }
      )
    ).toEqual({ lat: '-32.4', lng: '-62.7', zoom: '12', preset: 'agua', view: '3d', hazard: '1' });
  });
});
