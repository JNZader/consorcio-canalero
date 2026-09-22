/**
 * Staff-only IDECOR overlay — only features not in Red Vial 380.
 * Citizen never mounts the GeoJSON source.
 */

import { describe, expect, it, vi } from 'vitest';

import { LAYER_RENDER_REGISTRY } from '../../src/components/map2d/layerRenderRegistry';
import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import { syncRedVialOficialLayers } from '../../src/components/map2d/mapLayerEffectHelpers';
import {
  RED_VIAL_OFICIAL_ESTADO,
  RED_VIAL_OFICIAL_GEOJSON_URL,
  RED_VIAL_OFICIAL_LAYER_IDS,
  RED_VIAL_OFICIAL_PAINT,
  RED_VIAL_OFICIAL_SOURCE_ID,
  buildRedVialOficialEstadoFilter,
  buildRedVialOficialFaltaPaint,
} from '../../src/components/map2d/redVialOficialLayers';

function createMapMock() {
  const layers = new Set<string>();
  const sources = new Map<string, unknown>();
  return {
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    getSource: vi.fn((id: string) => sources.get(id)),
    addSource: vi.fn((id: string, source?: unknown) => {
      sources.set(id, source ?? { id });
    }),
    addLayer: vi.fn((layer: { id: string }) => {
      layers.add(layer.id);
    }),
    removeLayer: vi.fn((id: string) => {
      layers.delete(id);
    }),
    removeSource: vi.fn((id: string) => {
      sources.delete(id);
    }),
    setLayoutProperty: vi.fn(),
    layers,
    sources,
  };
}

describe('redVialOficialLayers · constants', () => {
  it('source id matches SOURCE_IDS.RED_VIAL_OFICIAL and the UI toggle key', () => {
    expect(RED_VIAL_OFICIAL_SOURCE_ID).toBe(SOURCE_IDS.RED_VIAL_OFICIAL);
    expect(RED_VIAL_OFICIAL_SOURCE_ID).toBe('red_vial_oficial');
  });

  it('loads the clip GeoJSON, not caminos.geojson', () => {
    expect(RED_VIAL_OFICIAL_GEOJSON_URL).toBe('/capas/red_vial_oficial_clip.geojson');
    expect(RED_VIAL_OFICIAL_GEOJSON_URL).not.toContain('caminos');
  });
});

describe('redVialOficialLayers · paint/filter uses estado', () => {
  it('filters the overlay on falta_en_padron', () => {
    expect(buildRedVialOficialEstadoFilter(RED_VIAL_OFICIAL_ESTADO.FALTA_EN_PADRON)).toEqual([
      '==',
      ['get', 'estado'],
      'falta_en_padron',
    ]);
  });

  it('paints falta_en_padron orange solid ~3px', () => {
    const paint = buildRedVialOficialFaltaPaint();
    expect(paint['line-color']).toBe('#ea580c');
    expect(paint['line-width']).toBe(3);
    expect(paint['line-opacity']).toBe(1);
    expect(paint['line-dasharray']).toBeUndefined();
    expect(RED_VIAL_OFICIAL_PAINT.falta_en_padron.color).toBe('#ea580c');
  });
});

describe('layerRenderRegistry · red_vial_oficial', () => {
  it('registers only the falta line layer', () => {
    expect(LAYER_RENDER_REGISTRY.red_vial_oficial.mlLayers).toEqual([
      {
        id: RED_VIAL_OFICIAL_LAYER_IDS.FALTA,
        opacityProp: 'line-opacity',
        defaultOpacity: 1,
      },
    ]);
  });
});

describe('syncRedVialOficialLayers · citizen never mounts', () => {
  it('does not add source or layers when shouldMount is false', () => {
    const map = createMapMock();
    syncRedVialOficialLayers(map as never, false, true);
    expect(map.addSource).not.toHaveBeenCalled();
    expect(map.addLayer).not.toHaveBeenCalled();
  });

  it('mounts only the falta layer for staff, not en_padron', () => {
    const map = createMapMock();
    syncRedVialOficialLayers(map as never, true, true);

    expect(map.addSource).toHaveBeenCalledWith(RED_VIAL_OFICIAL_SOURCE_ID, {
      type: 'geojson',
      data: RED_VIAL_OFICIAL_GEOJSON_URL,
    });

    const layers = map.addLayer.mock.calls.map(([layer]) => layer);
    expect(layers).toHaveLength(1);
    expect(layers[0].id).toBe(RED_VIAL_OFICIAL_LAYER_IDS.FALTA);
    expect(layers[0].filter).toEqual(['==', ['get', 'estado'], 'falta_en_padron']);
    expect(layers[0].paint?.['line-color']).toBe('#ea580c');
  });

  it('tears down source and layers when staff unmounts', () => {
    const map = createMapMock();
    syncRedVialOficialLayers(map as never, true, true);
    syncRedVialOficialLayers(map as never, false, false);
    expect(map.removeLayer).toHaveBeenCalledWith(RED_VIAL_OFICIAL_LAYER_IDS.FALTA);
    expect(map.removeSource).toHaveBeenCalledWith(RED_VIAL_OFICIAL_SOURCE_ID);
  });
});
