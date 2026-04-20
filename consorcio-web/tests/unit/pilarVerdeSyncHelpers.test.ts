/**
 * Sync-helpers unit tests for the 5 Pilar Verde MapLibre layers.
 *
 * Each helper MUST be idempotent:
 *   - First call: addSource + addLayer(fill) + addLayer(line) + setLayoutProperty(visible)
 *   - Second call with same args: only setLayoutProperty (no duplicate source/layer)
 *
 * Phase 7 — `syncBpaLayer` (single-year) was replaced by `syncBpaHistoricoLayer`
 * (unified historical series). After mount, `moveLayer(bpaHistoricoFillId)`
 * must be called (no beforeId) so click precedence lands on BPA over catastro.
 */

import type { FeatureCollection } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  syncAgroAceptadaLayer,
  syncAgroPresentadaLayer,
  syncAgroZonasLayer,
  syncBpaHistoricoLayer,
  syncPorcentajeForestacionLayer,
} from '../../src/components/map2d/mapLayerEffectHelpers';

function emptyCollection(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}

function createMapMock(options?: { layers?: string[]; sources?: string[] }) {
  const layers = new Set(options?.layers ?? []);
  const sources = new Set(options?.sources ?? []);

  return {
    layers,
    sources,
    map: {
      getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
      getSource: vi.fn((id: string) =>
        sources.has(id) ? { id, setData: vi.fn() } : undefined,
      ),
      addSource: vi.fn((id: string) => {
        sources.add(id);
      }),
      addLayer: vi.fn((layer: { id: string }) => {
        layers.add(layer.id);
      }),
      moveLayer: vi.fn(),
      setLayoutProperty: vi.fn(),
    },
  };
}

describe('syncBpaHistoricoLayer', () => {
  const bpaFill = `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-fill`;
  const bpaLine = `${SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO}-line`;

  it('mounts source + fill + line on first call, sets visible', () => {
    const { map } = createMapMock();
    syncBpaHistoricoLayer(map as never, emptyCollection(), true);

    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.addSource).toHaveBeenCalledWith(SOURCE_IDS.PILAR_VERDE_BPA_HISTORICO, expect.any(Object));

    const addLayerIds = map.addLayer.mock.calls.map((call) => (call[0] as { id: string }).id);
    expect(addLayerIds).toContain(bpaFill);
    expect(addLayerIds).toContain(bpaLine);

    expect(map.setLayoutProperty).toHaveBeenCalledWith(bpaFill, 'visibility', 'visible');
    expect(map.setLayoutProperty).toHaveBeenCalledWith(bpaLine, 'visibility', 'visible');
  });

  it('is idempotent — second call with same inputs does not duplicate source/layer', () => {
    const { map } = createMapMock();
    syncBpaHistoricoLayer(map as never, emptyCollection(), true);
    map.addSource.mockClear();
    map.addLayer.mockClear();

    syncBpaHistoricoLayer(map as never, emptyCollection(), false);

    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(bpaFill, 'visibility', 'none');
    expect(map.setLayoutProperty).toHaveBeenCalledWith(bpaLine, 'visibility', 'none');
  });

  it('raises bpa_historico-fill to the top (moveLayer with no beforeId) so clicks resolve BPA over catastro', () => {
    const { map } = createMapMock();
    syncBpaHistoricoLayer(map as never, emptyCollection(), true);

    const moveCalls = map.moveLayer.mock.calls;
    const fillMove = moveCalls.find((call) => call[0] === bpaFill);
    expect(fillMove).toBeTruthy();
    expect(fillMove?.[1]).toBeUndefined();
  });

  it('hidden state on first mount — sets visibility none instead of visible', () => {
    const { map } = createMapMock();
    syncBpaHistoricoLayer(map as never, emptyCollection(), false);
    expect(map.setLayoutProperty).toHaveBeenCalledWith(bpaFill, 'visibility', 'none');
  });

  it('accepts null collection — renders empty source rather than crashing', () => {
    const { map } = createMapMock();
    expect(() => syncBpaHistoricoLayer(map as never, null, true)).not.toThrow();
    expect(map.addSource).toHaveBeenCalled();
  });
});

describe('syncAgroAceptadaLayer', () => {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_ACEPTADA;
  it('mounts fill + line and is idempotent', () => {
    const { map } = createMapMock();
    syncAgroAceptadaLayer(map as never, emptyCollection(), true);
    expect(map.addLayer.mock.calls.map((c) => (c[0] as { id: string }).id)).toEqual(
      expect.arrayContaining([`${id}-fill`, `${id}-line`]),
    );

    map.addSource.mockClear();
    map.addLayer.mockClear();
    syncAgroAceptadaLayer(map as never, emptyCollection(), false);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(`${id}-fill`, 'visibility', 'none');
  });
});

describe('syncAgroPresentadaLayer', () => {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_PRESENTADA;
  it('mounts fill + line and is idempotent', () => {
    const { map } = createMapMock();
    syncAgroPresentadaLayer(map as never, emptyCollection(), true);
    expect(map.addLayer.mock.calls.map((c) => (c[0] as { id: string }).id)).toEqual(
      expect.arrayContaining([`${id}-fill`, `${id}-line`]),
    );

    map.addSource.mockClear();
    map.addLayer.mockClear();
    syncAgroPresentadaLayer(map as never, emptyCollection(), false);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(`${id}-fill`, 'visibility', 'none');
  });
});

describe('syncAgroZonasLayer', () => {
  const id = SOURCE_IDS.PILAR_VERDE_AGRO_ZONAS;
  it('mounts fill + line and is idempotent', () => {
    const { map } = createMapMock();
    syncAgroZonasLayer(map as never, emptyCollection(), true);
    expect(map.addLayer.mock.calls.map((c) => (c[0] as { id: string }).id)).toEqual(
      expect.arrayContaining([`${id}-fill`, `${id}-line`]),
    );

    map.addSource.mockClear();
    map.addLayer.mockClear();
    syncAgroZonasLayer(map as never, emptyCollection(), true);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
  });
});

describe('syncPorcentajeForestacionLayer', () => {
  const id = SOURCE_IDS.PILAR_VERDE_PORCENTAJE_FORESTACION;
  it('mounts fill (no line — context-only) and is idempotent', () => {
    const { map } = createMapMock();
    syncPorcentajeForestacionLayer(map as never, emptyCollection(), true);
    const addedIds = map.addLayer.mock.calls.map((c) => (c[0] as { id: string }).id);
    expect(addedIds).toContain(`${id}-fill`);
    // No line layer — this is a low-contrast background fill only.
    expect(addedIds).not.toContain(`${id}-line`);

    map.addSource.mockClear();
    map.addLayer.mockClear();
    syncPorcentajeForestacionLayer(map as never, emptyCollection(), false);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.setLayoutProperty).toHaveBeenCalledWith(`${id}-fill`, 'visibility', 'none');
  });
});
