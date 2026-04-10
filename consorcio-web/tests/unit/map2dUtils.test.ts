import type { Feature } from 'geojson';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  IGN_IMAGE_URL,
  IGN_MAPLIBRE_COORDS,
  asFeatureCollection,
  decorateFeature,
  ensureGeoJsonSource,
  formatExportFilename,
  leafletCenterToMapLibre,
  setLayerVisibility,
} from '../../src/components/map2d/map2dUtils';

describe('map2dUtils', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('converts Leaflet center coordinates to MapLibre order', () => {
    expect(leafletCenterToMapLibre([-32.62, -62.68])).toEqual([-62.68, -32.62]);
  });

  it('wraps features as a FeatureCollection', () => {
    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: { name: 'A' },
    };

    expect(asFeatureCollection([feature])).toEqual({
      type: 'FeatureCollection',
      features: [feature],
    });
  });

  it('decorates an existing feature with merged properties', () => {
    const feature: Feature = {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
      properties: { existing: 'yes' },
    };

    expect(decorateFeature(feature, { color: '#ff0000' })).toEqual({
      ...feature,
      properties: { existing: 'yes', color: '#ff0000' },
    });
  });

  it('updates an existing geojson source instead of re-adding it', () => {
    const setData = vi.fn();
    const map = {
      getSource: vi.fn(() => ({ setData })),
      addSource: vi.fn(),
    } as unknown as Parameters<typeof ensureGeoJsonSource>[0];

    const data = asFeatureCollection([]);
    ensureGeoJsonSource(map, 'source-id', data);

    expect(setData).toHaveBeenCalledWith(data);
    expect((map as { addSource: ReturnType<typeof vi.fn> }).addSource).not.toHaveBeenCalled();
  });

  it('adds a geojson source when it does not exist yet', () => {
    const addSource = vi.fn();
    const map = {
      getSource: vi.fn(() => undefined),
      addSource,
    } as unknown as Parameters<typeof ensureGeoJsonSource>[0];

    const data = asFeatureCollection([]);
    ensureGeoJsonSource(map, 'source-id', data);

    expect(addSource).toHaveBeenCalledWith('source-id', { type: 'geojson', data });
  });

  it('changes layer visibility only when the layer exists', () => {
    const setLayoutProperty = vi.fn();
    const map = {
      getLayer: vi.fn((id: string) => (id === 'visible-layer' ? { id } : undefined)),
      setLayoutProperty,
    } as unknown as Parameters<typeof setLayerVisibility>[0];

    setLayerVisibility(map, 'visible-layer', true);
    setLayerVisibility(map, 'missing-layer', false);

    expect(setLayoutProperty).toHaveBeenCalledTimes(1);
    expect(setLayoutProperty).toHaveBeenCalledWith('visible-layer', 'visibility', 'visible');
  });

  it('formats export filenames with normalized title and current date', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-04-09T12:00:00.000Z'));

    expect(formatExportFilename('Mapa Áreas Críticas', 'png')).toBe('mapa_areas_criticas_2026-04-09.png');
    expect(formatExportFilename('   ', 'pdf')).toBe('mapa_consorcio_2026-04-09.pdf');
  });

  it('exports IGN overlay constants', () => {
    expect(IGN_IMAGE_URL).toContain('altimetria_ign_consorcio.webp');
    expect(IGN_MAPLIBRE_COORDS).toHaveLength(4);
    expect(IGN_MAPLIBRE_COORDS[0]).toEqual([-62.750969, -32.44785]);
  });
});
