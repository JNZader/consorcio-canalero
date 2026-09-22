/**
 * Staff-only IDECOR official-road overlay — paint/filter contract + citizen
 * never-mounts the GeoJSON source.
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
  buildRedVialOficialEnPadronPaint,
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
  it('filters each layer on the estado property', () => {
    expect(buildRedVialOficialEstadoFilter(RED_VIAL_OFICIAL_ESTADO.FALTA_EN_PADRON)).toEqual([
      '==',
      ['get', 'estado'],
      'falta_en_padron',
    ]);
    expect(buildRedVialOficialEstadoFilter(RED_VIAL_OFICIAL_ESTADO.EN_PADRON)).toEqual([
      '==',
      ['get', 'estado'],
      'en_padron',
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

  it('paints en_padron green dashed ~2px at ~0.45 opacity', () => {
    const paint = buildRedVialOficialEnPadronPaint();
    expect(paint['line-color']).toBe('#22c55e');
    expect(paint['line-width']).toBe(2);
    expect(paint['line-opacity']).toBe(0.45);
    expect(paint['line-dasharray']).toEqual([2, 2]);
  });
});

describe('layerRenderRegistry · red_vial_oficial', () => {
  it('registers both estado line layers with the paint opacities', () => {
    expect(LAYER_RENDER_REGISTRY.red_vial_oficial.mlLayers).toEqual([
      {
        id: RED_VIAL_OFICIAL_LAYER_IDS.EN_PADRON,
        opacityProp: 'line-opacity',
        defaultOpacity: 0.45,
      },
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

  it('mounts the URL source and estado-filtered layers for staff', () => {
    const map = createMapMock();
    syncRedVialOficialLayers(map as never, true, true);

    expect(map.addSource).toHaveBeenCalledWith(RED_VIAL_OFICIAL_SOURCE_ID, {
      type: 'geojson',
      data: RED_VIAL_OFICIAL_GEOJSON_URL,
    });

    const layers = map.addLayer.mock.calls.map(([layer]) => layer);
    const falta = layers.find((layer) => layer.id === RED_VIAL_OFICIAL_LAYER_IDS.FALTA);
    const enPadron = layers.find((layer) => layer.id === RED_VIAL_OFICIAL_LAYER_IDS.EN_PADRON);
    expect(falta?.filter).toEqual(['==', ['get', 'estado'], 'falta_en_padron']);
    expect(falta?.paint?.['line-color']).toBe('#ea580c');
    expect(enPadron?.filter).toEqual(['==', ['get', 'estado'], 'en_padron']);
    expect(enPadron?.paint?.['line-color']).toBe('#22c55e');
  });

  it('tears down source and layers when staff unmounts', () => {
    const map = createMapMock();
    syncRedVialOficialLayers(map as never, true, true);
    syncRedVialOficialLayers(map as never, false, false);
    expect(map.removeLayer).toHaveBeenCalledWith(RED_VIAL_OFICIAL_LAYER_IDS.EN_PADRON);
    expect(map.removeLayer).toHaveBeenCalledWith(RED_VIAL_OFICIAL_LAYER_IDS.FALTA);
    expect(map.removeSource).toHaveBeenCalledWith(RED_VIAL_OFICIAL_SOURCE_ID);
  });
});
