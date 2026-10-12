import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it, vi } from 'vitest';

import { MAP_DEFAULT_ZOOM } from '../../src/constants';
import {
  applyLayerMinZoom,
  CATASTRO_LAYER_MIN_ZOOM,
  LAYER_ZOOM_IN_HINT,
  layerBelowMinZoom,
  SOIL_LAYER_MIN_ZOOM,
} from '../../src/components/map2d/layerMinZoom';
import { ROAD_LAYER_LABEL, ROAD_LAYER_LEGEND_LABEL } from '../../src/components/map2d/mapLayerLabels';

describe('CART-06 layer minzoom', () => {
  it('hides catastro and soils at the opening camera', () => {
    expect(MAP_DEFAULT_ZOOM).toBe(11);
    expect(CATASTRO_LAYER_MIN_ZOOM).toBe(12);
    expect(SOIL_LAYER_MIN_ZOOM).toBe(12);
    expect(layerBelowMinZoom('catastro', MAP_DEFAULT_ZOOM)).toBe(true);
    expect(layerBelowMinZoom('soil', MAP_DEFAULT_ZOOM)).toBe(true);
    expect(layerBelowMinZoom('catastro', 12)).toBe(false);
    expect(layerBelowMinZoom('roads', MAP_DEFAULT_ZOOM)).toBe(false);
  });

  it('sets MapLibre zoom range when the layer exists', () => {
    const setLayerZoomRange = vi.fn();
    applyLayerMinZoom(
      { getLayer: (id) => (id === 'map2d-catastro-fill' ? {} : null), setLayerZoomRange },
      'map2d-catastro-fill',
      12
    );
    expect(setLayerZoomRange).toHaveBeenCalledWith('map2d-catastro-fill', 12, 24);
  });

  it('exposes the panel hint copy', () => {
    expect(LAYER_ZOOM_IN_HINT).toBe('Acercate para ver esta capa');
  });
});

describe('CART-08 rural road copy', () => {
  it('does not call the layer Red Vial', () => {
    expect(ROAD_LAYER_LABEL).toBe('Red vial rural');
    expect(ROAD_LAYER_LEGEND_LABEL).toBe('Red vial rural del consorcio');
  });
});

describe('PERF-02 chart chunks', () => {
  it('does not statically import chart modules from the ficha parents', () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const ficha = readFileSync(
      join(here, '../../src/components/map2d/FichaTerritorialPanel.tsx'),
      'utf8'
    );
    const lluvia = readFileSync(
      join(here, '../../src/components/map2d/rainfall/RainfallDetailPanel.tsx'),
      'utf8'
    );
    expect(ficha).not.toMatch(/import \{ PrecipChart \}/);
    expect(ficha).toMatch(/lazy\(async/);
    expect(lluvia).not.toMatch(/from '\.\/RainfallAccumulationChart'/);
    expect(lluvia).toMatch(/from '\.\/rainfallCampaign'/);
    expect(lluvia).toMatch(/lazy\(async/);
  });
});
