import type { FeatureCollection } from 'geojson';
import { describe, expect, it, vi } from 'vitest';

import { SOURCE_IDS } from '../../src/components/map2d/map2dConfig';
import {
  shouldShowSuggestedZones,
  syncBaseTileVisibility,
  syncCatastroLayers,
  syncSoilLayers,
} from '../../src/components/map2d/mapLayerEffectHelpers';
import {
  getVisibleRasterLayersForDem,
  syncDemRasterLayer,
  syncImageOverlays,
} from '../../src/components/map2d/mapRasterOverlayHelpers';

function emptyCollection(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] };
}

function createMapMock(options?: {
  layers?: string[];
  sources?: string[];
}) {
  const layers = new Set(options?.layers ?? []);
  const sources = new Set(options?.sources ?? []);

  return {
    getLayer: vi.fn((id: string) => (layers.has(id) ? { id } : undefined)),
    getSource: vi.fn((id: string) => (sources.has(id) ? { id } : undefined)),
    addSource: vi.fn((id: string) => {
      sources.add(id);
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
  };
}

describe('mapLayerEffectHelpers', () => {
  it('computes when suggested zones should be visible', () => {
    expect(
      shouldShowSuggestedZones({
        showSuggestedZonesPanel: true,
        hasApprovedZones: false,
        suggestedZonesDisplay: emptyCollection(),
      }),
    ).toBe(true);

    expect(
      shouldShowSuggestedZones({
        showSuggestedZonesPanel: true,
        hasApprovedZones: true,
        suggestedZonesDisplay: emptyCollection(),
      }),
    ).toBe(false);
  });

  it('returns the visible DEM raster layer metadata only when overlay is active', () => {
    const layers = [
      { id: 'dem-1', tipo: 'slope', nombre: 'Pendiente' },
      { id: 'dem-2', tipo: 'aspect', nombre: 'Orientacion' },
    ];

    expect(getVisibleRasterLayersForDem(layers, true, 'dem-2')).toEqual([{ tipo: 'aspect' }]);
    expect(getVisibleRasterLayersForDem(layers, false, 'dem-2')).toEqual([]);
    expect(getVisibleRasterLayersForDem(layers, true, 'missing')).toEqual([]);
  });

  it('toggles the correct base tile visibility', () => {
    const map = createMapMock({ layers: ['osm-tiles', 'satellite-tiles'] });

    syncBaseTileVisibility(map as never, 'satellite');

    expect(map.setLayoutProperty).toHaveBeenNthCalledWith(
      1,
      'osm-tiles',
      'visibility',
      'none',
    );
    expect(map.setLayoutProperty).toHaveBeenNthCalledWith(
      2,
      'satellite-tiles',
      'visibility',
      'visible',
    );
  });

  it('replaces single-image overlay sources when single view is active', () => {
    const map = createMapMock({
      layers: [`${SOURCE_IDS.SATELLITE_IMAGE}-layer`],
      sources: [SOURCE_IDS.SATELLITE_IMAGE],
    });

    syncImageOverlays(map as never, {
      viewMode: 'single',
      selectedImage: { tile_url: 'https://tiles.example.com/single/{z}/{x}/{y}.png' },
      comparison: null,
    });

    expect(map.removeLayer).toHaveBeenCalledWith(`${SOURCE_IDS.SATELLITE_IMAGE}-layer`);
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_IDS.SATELLITE_IMAGE);
    expect(map.addSource).toHaveBeenCalledWith(SOURCE_IDS.SATELLITE_IMAGE, {
      type: 'raster',
      tiles: ['https://tiles.example.com/single/{z}/{x}/{y}.png'],
      tileSize: 256,
    });
  });

  it('cleans comparison overlays when not in comparison mode', () => {
    const map = createMapMock({
      layers: [
        `${SOURCE_IDS.COMPARISON_LEFT}-layer`,
        `${SOURCE_IDS.COMPARISON_RIGHT}-layer`,
      ],
      sources: [SOURCE_IDS.COMPARISON_LEFT, SOURCE_IDS.COMPARISON_RIGHT],
    });

    syncImageOverlays(map as never, {
      viewMode: 'base',
      selectedImage: null,
      comparison: null,
    });

    expect(map.removeLayer).toHaveBeenCalledWith(`${SOURCE_IDS.COMPARISON_LEFT}-layer`);
    expect(map.removeLayer).toHaveBeenCalledWith(`${SOURCE_IDS.COMPARISON_RIGHT}-layer`);
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_IDS.COMPARISON_LEFT);
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_IDS.COMPARISON_RIGHT);
  });

  it('keeps only the right raster overlay on the base map during comparison mode', () => {
    const map = createMapMock({
      layers: [`${SOURCE_IDS.COMPARISON_LEFT}-layer`],
      sources: [SOURCE_IDS.COMPARISON_LEFT],
    });

    syncImageOverlays(map as never, {
      viewMode: 'comparison',
      selectedImage: null,
      comparison: {
        left: { tile_url: 'https://tiles.example.com/left/{z}/{x}/{y}.png' },
        right: { tile_url: 'https://tiles.example.com/right/{z}/{x}/{y}.png' },
      },
    });

    expect(map.removeLayer).toHaveBeenCalledWith(`${SOURCE_IDS.COMPARISON_LEFT}-layer`);
    expect(map.removeSource).toHaveBeenCalledWith(SOURCE_IDS.COMPARISON_LEFT);
    expect(map.addSource).toHaveBeenCalledWith(SOURCE_IDS.COMPARISON_RIGHT, {
      type: 'raster',
      tiles: ['https://tiles.example.com/right/{z}/{x}/{y}.png'],
      tileSize: 256,
    });
  });

  // ── Layer-visibility audit (paint constants) ────────────────────────────
  // Lock the high-contrast paint values against accidental regression. These
  // values were chosen so cadastral and soil detail stay readable on BOTH
  // satellite and OSM base layers.
  it('renders the catastro line with a white high-contrast outline on first mount', () => {
    const map = createMapMock();

    syncCatastroLayers(map as never, true);

    const catastroLineCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${SOURCE_IDS.CATASTRO}-line`,
    );
    expect(catastroLineCall).toBeDefined();
    const [catastroLineLayer] = catastroLineCall ?? [];
    expect(catastroLineLayer?.paint).toMatchObject({
      'line-color': '#FFFFFF',
      'line-width': 1.5,
      'line-opacity': 0.85,
    });
  });

  it('renders the soil fill and line with the audited visibility-boost paint', () => {
    const map = createMapMock();

    syncSoilLayers(map as never, emptyCollection(), true);

    const fillCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${SOURCE_IDS.SOIL}-fill`,
    );
    expect(fillCall).toBeDefined();
    const [fillLayer] = fillCall ?? [];
    expect(fillLayer?.paint).toMatchObject({
      'fill-opacity': 0.3,
    });

    const lineCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${SOURCE_IDS.SOIL}-line`,
    );
    expect(lineCall).toBeDefined();
    const [lineLayer] = lineCall ?? [];
    expect(lineLayer?.paint).toMatchObject({
      'line-color': '#6d4c41',
      'line-width': 1.2,
      'line-opacity': 0.85,
    });
  });

  it('mounts the DEM raster layer with the audited 0.6 opacity', () => {
    const map = createMapMock();

    syncDemRasterLayer(map as never, {
      showDemOverlay: true,
      activeDemLayerId: 'dem-1',
      demTileUrl: 'https://tiles.example.com/dem/{z}/{x}/{y}.png',
    });

    const demCall = map.addLayer.mock.calls.find(
      ([layer]) => layer?.id === `${SOURCE_IDS.DEM_RASTER}-layer`,
    );
    expect(demCall).toBeDefined();
    const [demLayer] = demCall ?? [];
    expect(demLayer?.paint).toMatchObject({
      'raster-opacity': 0.6,
    });
  });
});
