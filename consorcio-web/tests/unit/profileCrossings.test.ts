import { describe, expect, it } from 'vitest';
import { dedupeCrossings } from '../../src/components/map2d/ElevationProfileChart';

describe('dedupeCrossings', () => {
  it('keeps distinct labels that sit inside 20 m and collapses only parcel hits', () => {
    const kept = dedupeCrossings([
      { distance_m: 100, label: 'Alcantarilla' },
      { distance_m: 110, label: 'Parcela 12' },
      { distance_m: 118, label: 'Parcela 12 bis' },
      { distance_m: 200, label: 'Camino rural' },
    ]);

    expect(kept.map((hit) => hit.label)).toEqual(['Alcantarilla', 'Parcela 12', 'Camino rural']);
  });
});
