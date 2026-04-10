import { describe, expect, it } from 'vitest';

import type { CanalSuggestion } from '../../src/lib/api';
import {
  buildMapCollections,
  buildSuggestionStats,
  collectBoundsCoordinates,
  createVisibleTypesSet,
  extractGeometry,
  getDescription,
  getMaintenanceColor,
  getScoreColor,
  sortSuggestions,
} from '../../src/components/admin/canal-suggestions/canalSuggestionsUtils';

const baseSuggestion = (overrides: Partial<CanalSuggestion> = {}): CanalSuggestion => ({
  id: '1',
  tipo: 'hotspot',
  score: 80,
  metadata: null,
  batch_id: 'batch-1',
  created_at: '2026-04-09T19:00:00.000Z',
  ...overrides,
});

describe('canalSuggestionsUtils', () => {
  it('extracts descriptions and colors', () => {
    expect(getDescription(baseSuggestion({ metadata: { description: 'Zona critica' } }))).toBe('Zona critica');
    expect(getDescription(baseSuggestion({ metadata: { gap_km: 3.25 } }))).toBe('Distancia al canal: 3.3 km');
    expect(getDescription(baseSuggestion())).toBe('-');
    expect(getScoreColor(80)).toBe('red');
    expect(getScoreColor(55)).toBe('orange');
    expect(getScoreColor(30)).toBe('yellow');
    expect(getScoreColor(10)).toBe('green');
    expect(getMaintenanceColor(0.8)).toBe('#e03131');
    expect(getMaintenanceColor(0.5)).toBe('#f08c00');
    expect(getMaintenanceColor(0.1)).toBe('#2f9e44');
  });

  it('extracts geometry from geojson and fallback metadata', () => {
    expect(
      extractGeometry(baseSuggestion({ metadata: { geometry: { type: 'Point', coordinates: [-58.5, -34.6] } } })),
    ).toEqual({ type: 'point', lat: -34.6, lng: -58.5 });

    expect(
      extractGeometry(baseSuggestion({ metadata: { lat: -34.5, lng: -58.4 } })),
    ).toEqual({ type: 'point', lat: -34.5, lng: -58.4 });

    expect(
      extractGeometry(
        baseSuggestion({
          metadata: { geometry: { type: 'LineString', coordinates: [[-58.4, -34.5], [-58.3, -34.4]] } },
        }),
      ),
    ).toEqual({ type: 'line', positions: [[-34.5, -58.4], [-34.4, -58.3]] });
  });

  it('sorts suggestions and builds stats', () => {
    const suggestions = [
      baseSuggestion({ id: '1', score: 20, tipo: 'gap' }),
      baseSuggestion({ id: '2', score: 80, tipo: 'hotspot' }),
    ];
    expect(sortSuggestions(suggestions, 'desc').map((item) => item.id)).toEqual(['2', '1']);
    expect(sortSuggestions(suggestions, 'asc').map((item) => item.id)).toEqual(['1', '2']);
    expect(buildSuggestionStats(suggestions)).toEqual({ gap: 1, hotspot: 1 });
  });

  it('builds map collections and bounds', () => {
    const suggestions = [
      baseSuggestion({
        id: 'pt',
        tipo: 'hotspot',
        metadata: { geometry: { type: 'Point', coordinates: [-58.5, -34.6] } },
      }),
      baseSuggestion({
        id: 'ln',
        tipo: 'route',
        score: 40,
        metadata: { geometry: { type: 'LineString', coordinates: [[-58.4, -34.5], [-58.3, -34.4]] } },
      }),
    ];

    const visibleTypes = createVisibleTypesSet();
    const { filtered, pointFeatures, lineFeatures } = buildMapCollections(suggestions, visibleTypes);
    expect(filtered).toHaveLength(2);
    expect(pointFeatures).toHaveLength(1);
    expect(lineFeatures).toHaveLength(1);
    expect(collectBoundsCoordinates(pointFeatures, lineFeatures)).toEqual([
      [-58.5, -34.6],
      [-58.4, -34.5],
      [-58.3, -34.4],
    ]);
  });
});
