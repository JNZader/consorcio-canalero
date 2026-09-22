import type { FeatureCollection, LineString } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

vi.mock('maplibre-gl', () => ({
  default: { Map: vi.fn(), Popup: vi.fn(), LngLatBounds: vi.fn() },
}));

import { patchConsorcioFeature } from '../../src/components/admin/CanalesPublicacionMap';

function collection(publicado: boolean): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        id: 'canal-1',
        geometry: { type: 'LineString', coordinates: [[-62.5, -32.5], [-62.4, -32.4]] },
        properties: { id: 'canal-1', publicado, nombre_publico: 'Viejo' },
      },
      {
        type: 'Feature',
        id: 'canal-2',
        geometry: { type: 'LineString', coordinates: [[-62.3, -32.3], [-62.2, -32.2]] },
        properties: { id: 'canal-2', publicado: true, nombre_publico: 'Otro' },
      },
    ],
  };
}

describe('patchConsorcioFeature', () => {
  it('toggles publicado only on the selected canal', () => {
    const next = patchConsorcioFeature(collection(true), 'canal-1', { publicado: false });
    expect(next.features[0].properties?.publicado).toBe(false);
    expect(next.features[1].properties?.publicado).toBe(true);
  });

  it('renames the public label without touching geometry', () => {
    const before = collection(true);
    const next = patchConsorcioFeature(before, 'canal-1', { nombre_publico: 'Canal 10 de Mayo' });
    expect(next.features[0].properties?.nombre_publico).toBe('Canal 10 de Mayo');
    expect(next.features[0].geometry).toEqual(before.features[0].geometry);
  });
});
