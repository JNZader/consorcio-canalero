/**
 * ypfEstacionBombeoLayer.test.ts
 *
 * Unit tests for the hardcoded "Estación de bombeo YPF" static landmark.
 *
 * Sibling of `escuelasLayers.ts` but radically simpler: one feature, no KMZ,
 * no ETL, no async asset pipeline, no toggle. The layer is ALWAYS visible
 * from map init; the legend chip is ALWAYS rendered.
 *
 * What we pin here:
 *   - Source + layer ids.
 *   - Hardcoded color (`#d84315` Material Deep Orange 800).
 *   - GeoJSON shape: exactly one Point at `[-62.5436402, -32.5728979]`.
 *   - Circle paint factory — zoom-interpolated radius slightly larger than the
 *     escuelas circles (5→9 vs. 4→8) so the landmark reads more prominent.
 */

import { describe, expect, it } from 'vitest';

import {
  YPF_ESTACION_BOMBEO_COLOR,
  YPF_ESTACION_BOMBEO_GEOJSON,
  YPF_ESTACION_BOMBEO_LABEL,
  YPF_ESTACION_BOMBEO_LAYER_ID,
  YPF_ESTACION_BOMBEO_SOURCE_ID,
  buildYpfEstacionBombeoPaint,
} from '../../src/components/map2d/ypfEstacionBombeoLayer';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

describe('ypfEstacionBombeoLayer · constants', () => {
  it('exposes the canonical source id `ypf-estacion-bombeo`', () => {
    expect(YPF_ESTACION_BOMBEO_SOURCE_ID).toBe('ypf-estacion-bombeo');
  });

  it('exposes the canonical layer id `ypf-estacion-bombeo-circle`', () => {
    expect(YPF_ESTACION_BOMBEO_LAYER_ID).toBe('ypf-estacion-bombeo-circle');
  });

  it('exposes the Spanish display label', () => {
    expect(YPF_ESTACION_BOMBEO_LABEL).toBe('Estación de bombeo YPF');
  });

  it('exposes the Material Deep Orange 800 color `#d84315`', () => {
    expect(YPF_ESTACION_BOMBEO_COLOR).toBe('#d84315');
  });
});

// ---------------------------------------------------------------------------
// GeoJSON shape
// ---------------------------------------------------------------------------

describe('YPF_ESTACION_BOMBEO_GEOJSON', () => {
  it('is a FeatureCollection with exactly one feature', () => {
    expect(YPF_ESTACION_BOMBEO_GEOJSON.type).toBe('FeatureCollection');
    expect(YPF_ESTACION_BOMBEO_GEOJSON.features).toHaveLength(1);
  });

  it('is a Point at [-62.5436402, -32.5728979] (GeoJSON order: lng, lat)', () => {
    const feature = YPF_ESTACION_BOMBEO_GEOJSON.features[0]!;
    expect(feature.type).toBe('Feature');
    expect(feature.geometry.type).toBe('Point');
    expect(feature.geometry.coordinates).toEqual([-62.5436402, -32.5728979]);
  });

  it('carries a minimal `nombre` property for InfoPanel fallback and no PII', () => {
    const feature = YPF_ESTACION_BOMBEO_GEOJSON.features[0]!;
    expect(feature.properties).toEqual({ nombre: 'Estación de bombeo YPF' });
  });
});

// ---------------------------------------------------------------------------
// Circle paint factory — visual contract
// ---------------------------------------------------------------------------

describe('buildYpfEstacionBombeoPaint', () => {
  it('uses a zoom-interpolated circle-radius from 5 @ z10 to 9 @ z16', () => {
    // Slightly larger than escuelas (4→8) so the single landmark reads as
    // more prominent against the cluster of blue school circles.
    const paint = buildYpfEstacionBombeoPaint();
    expect(paint['circle-radius']).toEqual([
      'interpolate',
      ['linear'],
      ['zoom'],
      10,
      5,
      16,
      9,
    ]);
  });

  it('fills the circle in `#d84315` (Material Deep Orange 800)', () => {
    const paint = buildYpfEstacionBombeoPaint();
    expect(paint['circle-color']).toBe('#d84315');
  });

  it('strokes the circle with a 2px white outline so it reads on any basemap', () => {
    const paint = buildYpfEstacionBombeoPaint();
    expect(paint['circle-stroke-color']).toBe('#ffffff');
    expect(paint['circle-stroke-width']).toBe(2);
  });
});
