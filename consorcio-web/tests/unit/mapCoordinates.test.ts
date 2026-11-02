import { describe, expect, it } from 'vitest';

import { inCordoba, parseCoordinateQuery } from '../../src/components/map2d/mapCoordinates';
import { rememberSearch, readRecentSearches } from '../../src/components/map2d/mapSearchHistory';
import { elevationAxisDomain, profileToCsv } from '../../src/components/map2d/profileFormat';
import { parseMapPermalink, selectionPermalinkToken } from '../../src/components/map2d/mapPermalink';

describe('parseCoordinateQuery', () => {
  it('reads decimal lat, lon inside Córdoba', () => {
    const read = parseCoordinateQuery('-32.41, -64.18');
    expect(read?.ok).toBe(true);
    if (read?.ok) {
      expect(read.point.lat).toBeCloseTo(-32.41);
      expect(read.point.lon).toBeCloseTo(-64.18);
    }
  });

  it('detects lon, lat when that is the order that lands in Córdoba', () => {
    const read = parseCoordinateQuery('-64.18, -32.41');
    expect(read?.ok).toBe(true);
    if (read?.ok) {
      expect(read.point.lat).toBeCloseTo(-32.41);
      expect(read.point.lon).toBeCloseTo(-64.18);
    }
  });

  it('reads DMS with south and west', () => {
    const read = parseCoordinateQuery('32°24\'36"S 64°10\'48"W');
    expect(read?.ok).toBe(true);
    if (read?.ok) {
      expect(read.point.lat).toBeCloseTo(-(32 + 24 / 60 + 36 / 3600), 4);
      expect(read.point.lon).toBeCloseTo(-(64 + 10 / 60 + 48 / 3600), 4);
      expect(inCordoba(read.point.lat, read.point.lon)).toBe(true);
    }
  });

  it('rejects a point outside the province', () => {
    expect(parseCoordinateQuery('-34.6, -58.4')).toEqual({ ok: false, reason: 'out-of-bounds' });
  });

  it('ignores ordinary search text', () => {
    expect(parseCoordinateQuery('canal norte')).toBeNull();
  });
});

describe('recent searches', () => {
  it('keeps the latest query first and drops duplicates', () => {
    localStorage.clear();
    rememberSearch('canal norte');
    rememberSearch('-32.4, -64.2');
    rememberSearch('canal norte');
    expect(readRecentSearches().slice(0, 2)).toEqual(['canal norte', '-32.4, -64.2']);
  });
});

describe('profile axis and csv', () => {
  it('pads a 2 m relief so the axis is not the whole plot', () => {
    const [lo, hi] = elevationAxisDomain(100, 102);
    expect(hi - lo).toBeGreaterThan(10);
    expect(lo).toBeLessThan(100);
    expect(hi).toBeGreaterThan(102);
  });

  it('writes a csv with an empty cell for a missing sample', () => {
    expect(profileToCsv([{ distance_m: 0, elevation_m: 110 }, { distance_m: 30, elevation_m: null }])).toBe(
      'distancia_m,cota_m\n0,110\n30,\n'
    );
  });
});

describe('selection permalink', () => {
  it('prefers the parcel account', () => {
    expect(
      selectionPermalinkToken({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: { Nro_Cuenta: '12-3' },
      })
    ).toBe('cuenta:12-3');
  });

  it('round-trips sel', () => {
    expect(parseMapPermalink('?sel=cuenta:12-3').sel).toBe('cuenta:12-3');
    expect(parseMapPermalink('?sel=canal:norte').sel).toBe('canal:norte');
  });
});
