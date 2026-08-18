import { describe, expect, it } from 'vitest';
import { defaultStringifySearch } from '@tanstack/react-router';

import {
  HAZARD_ROUTE_MARKER,
  isHazardSearchState,
  parseRiskClasses,
  stringifySearch,
  validateMapaSearch,
} from '@/lib/mapaSearchSerialization';

/** Parse a `?...` query string into a list of `[key, value]` pairs. */
function entries(url: string): Array<[string, string]> {
  const qs = url.startsWith('?') ? url.slice(1) : url;
  return Array.from(new URLSearchParams(qs).entries());
}

function markerKeyPresent(url: string): boolean {
  return url.includes('hazardRouteMarker') || url.includes('consorcio.');
}

describe('H5 — /mapa search serialization is route-scoped via internal marker', () => {
  describe('isHazardSearchState gate', () => {
    it('is true only for objects carrying the internal marker', () => {
      const marked = validateMapaSearch({ hazard: '1' });
      expect(isHazardSearchState(marked)).toBe(true);
    });

    it('is false for a plain object with generic hazard/basin keys (no marker)', () => {
      expect(isHazardSearchState({ hazard: true, basin: 'x' })).toBe(false);
    });

    it('is false for null / non-object input', () => {
      expect(isHazardSearchState(null)).toBe(false);
      expect(isHazardSearchState(undefined)).toBe(false);
      expect(isHazardSearchState('hazard=1')).toBe(false);
    });
  });

  describe('/mapa hazard round-trip and repeated params', () => {
    it('serializes the canonical public URL shape', () => {
      const state = validateMapaSearch({
        hazard: '1',
        basin: 'cuenca-1',
        riskClasses: ['Bajo', 'Medio'],
        layers: ['flood_risk'],
        precipMonth: 'anual',
      });

      const url = stringifySearch(state);

      // hazard -> `1`, basin present, repeated riskClasses as separate params,
      // layers present, default precipMonth=anual omitted.
      expect(url).toBe('?hazard=1&basin=cuenca-1&riskClasses=Bajo&riskClasses=Medio&layers=flood_risk');
    });

    it('emits repeated riskClasses as separate params (not JSON)', () => {
      const state = validateMapaSearch({ hazard: '1', riskClasses: ['Bajo', 'Medio', 'Alto'] });
      const url = stringifySearch(state);

      const riskPairs = entries(url).filter(([k]) => k === 'riskClasses');
      expect(riskPairs).toEqual([
        ['riskClasses', 'Bajo'],
        ['riskClasses', 'Medio'],
        ['riskClasses', 'Alto'],
      ]);
      expect(url).not.toContain('[');
    });

    it('omits the default precipMonth=anual but keeps a non-default month', () => {
      const def = validateMapaSearch({ hazard: '1', precipMonth: 'anual' });
      expect(stringifySearch(def)).not.toContain('precipMonth');

      const jun = validateMapaSearch({ hazard: '1', precipMonth: '06' });
      expect(stringifySearch(jun)).toContain('precipMonth=06');
    });

    it('keeps optional layers and drops empty arrays', () => {
      const withLayers = validateMapaSearch({ hazard: '1', layers: ['soil'] });
      expect(stringifySearch(withLayers)).toContain('layers=soil');

      const noLayers = validateMapaSearch({ hazard: '1', layers: [] });
      expect(stringifySearch(noLayers)).not.toContain('layers');
    });
  });

  describe('internal marker never appears in the URL', () => {
    it('strips the marker from the serialized output', () => {
      const state = validateMapaSearch({ hazard: '1', basin: 'x', riskClasses: ['Bajo'] });
      const url = stringifySearch(state);

      expect(markerKeyPresent(url)).toBe(false);
      // The marker is still present on the in-memory object.
      expect((state as Record<symbol, unknown>)[HAZARD_ROUTE_MARKER]).toBe(true);
      // URLSearchParams / Object.entries never expose a Symbol key.
      expect(entries(url).some(([k]) => k === String(HAZARD_ROUTE_MARKER))).toBe(false);
    });
  });

  describe('non-map search objects use the default serializer exactly', () => {
    it('layers array on a non-map object is JSON-stringified by default', () => {
      const url = stringifySearch({ layers: ['a', 'b'] });
      expect(url).toBe(defaultStringifySearch({ layers: ['a', 'b'] }));
      // Default uses a single JSON-encoded param, not repeated params.
      expect(entries(url).filter(([k]) => k === 'layers')).toHaveLength(1);
      expect(url).toContain('%5B%22a%22%2C%22b%22%5D');
    });

    it('layers object on a non-map object is JSON-stringified by default', () => {
      const url = stringifySearch({ layers: { foo: 'bar' } });
      expect(url).toBe(defaultStringifySearch({ layers: { foo: 'bar' } }));
      expect(url).toContain('%7B%22foo%22%3A%22bar%22%7D');
    });

    it('generic hazard/basin keys WITHOUT the marker use the default writer', () => {
      const url = stringifySearch({ hazard: true, basin: 'x' });
      // Default stringifies booleans as `true`, NOT `hazard=1`.
      expect(url).toBe(defaultStringifySearch({ hazard: true, basin: 'x' }));
      expect(url).toContain('hazard=true');
      expect(url).not.toContain('hazard=1');
    });

    it('a non-map object sharing ALL hazard keys still falls back to default', () => {
      const url = stringifySearch({
        hazard: true,
        basin: 'x',
        riskClasses: ['Bajo'],
        layers: ['flood_risk'],
        precipMonth: 'anual',
      });
      expect(url).toBe(
        defaultStringifySearch({
          hazard: true,
          basin: 'x',
          riskClasses: ['Bajo'],
          layers: ['flood_risk'],
          precipMonth: 'anual',
        }),
      );
      expect(url).not.toContain('hazard=1');
      expect(url).toContain('hazard=true');
    });
  });

  describe('legacy /mapa parser remains green', () => {
    it('parses JSON-array riskClasses', () => {
      expect(parseRiskClasses('["Bajo","Medio"]')).toEqual(['Bajo', 'Medio']);
    });

    it('treats empty / "[]" as empty', () => {
      expect(parseRiskClasses('[]')).toEqual([]);
      expect(parseRiskClasses('')).toEqual([]);
    });

    it('parses CSV / semicolon-separated values', () => {
      expect(parseRiskClasses('Bajo;Medio')).toEqual(['Bajo', 'Medio']);
      expect(parseRiskClasses('Bajo,Alto')).toEqual(['Bajo', 'Alto']);
    });

    it('parses native arrays and undefined', () => {
      expect(parseRiskClasses(['Alto'])).toEqual(['Alto']);
      expect(parseRiskClasses(undefined)).toEqual([]);
    });

    it('validateMapaSearch preserves legacy parsing and attaches the marker', () => {
      const state = validateMapaSearch({
        hazard: '1',
        riskClasses: '["Bajo","Medio"]',
        layers: [],
      });

      expect(state.hazard).toBe(true);
      expect(state.riskClasses).toEqual(['Bajo', 'Medio']);
      expect(state.layers).toEqual([]);
      expect(state.precipMonth).toBe('anual');
      expect((state as Record<symbol, unknown>)[HAZARD_ROUTE_MARKER]).toBe(true);
      // No visible key leaks the marker name.
      expect(Object.keys(state)).not.toContain('consorcio.hazardRouteMarker');
    });
  });
});
