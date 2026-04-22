/**
 * Unit tests for measurement draw modes config.
 *
 * Module under test:
 *   src/components/map2d/measurement/measurementDrawModes.ts
 *
 * Scope (Batch B of the map-measurement-tools SDD):
 * - Locks the shape of MEASUREMENT_DRAW_OPTIONS (fed to `new MapboxDraw(...)`).
 * - Locks the style entries in MEASUREMENT_DRAW_STYLES — specifically that
 *   we have style rules for LineString, Polygon, and Point geometries, and
 *   that they use the measurement accent color (Mantine orange 6) instead
 *   of the canales blue `#1971c2`.
 * - Locks the `createMeasurementDraw` factory: it must construct a fresh
 *   MapboxDraw instance passing the MEASUREMENT_DRAW_OPTIONS exactly.
 *
 * The dedicated draw instance (NOT shared with LineDrawControl) is a
 * proposal-level invariant — Batch C's integration relies on this.
 */

import { describe, expect, it, vi } from 'vitest';

// Mock @mapbox/mapbox-gl-draw BEFORE importing the module under test, so
// we can spy on the constructor and assert the options passed.
const mapboxDrawConstructorSpy = vi.fn();

vi.mock('@mapbox/mapbox-gl-draw', () => {
  class MapboxDrawMock {
    constructor(options?: unknown) {
      mapboxDrawConstructorSpy(options);
    }
  }
  return { default: MapboxDrawMock };
});

// Import AFTER the mock is registered.
import {
  createMeasurementDraw,
  MEASUREMENT_DRAW_OPTIONS,
  MEASUREMENT_DRAW_STYLES,
} from '@/components/map2d/measurement/measurementDrawModes';

describe('measurementDrawModes', () => {
  describe('MEASUREMENT_DRAW_OPTIONS', () => {
    it('has displayControlsDefault = false (toolbar drives modes, not built-in controls)', () => {
      expect(MEASUREMENT_DRAW_OPTIONS.displayControlsDefault).toBe(false);
    });

    it('has controls = {} so no auto-rendered controls leak onto the map', () => {
      expect(MEASUREMENT_DRAW_OPTIONS.controls).toEqual({});
    });

    it('wires MEASUREMENT_DRAW_STYLES into the styles option', () => {
      expect(MEASUREMENT_DRAW_OPTIONS.styles).toBe(MEASUREMENT_DRAW_STYLES);
    });

    it('enables userProperties (lets our own `properties.type` tagging survive)', () => {
      expect(MEASUREMENT_DRAW_OPTIONS.userProperties).toBe(true);
    });
  });

  describe('MEASUREMENT_DRAW_STYLES', () => {
    it('is a non-empty array', () => {
      expect(Array.isArray(MEASUREMENT_DRAW_STYLES)).toBe(true);
      expect(MEASUREMENT_DRAW_STYLES.length).toBeGreaterThan(0);
    });

    it('contains at least one line-type style (for LineString features)', () => {
      const lineStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'line',
      );
      expect(lineStyles.length).toBeGreaterThan(0);
    });

    it('contains at least one fill-type style (for Polygon features)', () => {
      const fillStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'fill',
      );
      expect(fillStyles.length).toBeGreaterThan(0);
    });

    it('contains at least one circle-type style (for Point / vertex features)', () => {
      const circleStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'circle',
      );
      expect(circleStyles.length).toBeGreaterThan(0);
    });

    it('uses the measurement accent #fd7e14 (Mantine orange 6) on at least one line style', () => {
      const lineStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'line',
      );
      const hasOrangeAccent = lineStyles.some((style) => {
        const paint = (style as { paint?: Record<string, unknown> }).paint ?? {};
        return paint['line-color'] === '#fd7e14';
      });
      expect(hasOrangeAccent).toBe(true);
    });

    it('uses line-width 3 on at least one line style (distinct from canales width 4)', () => {
      const lineStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'line',
      );
      const hasWidth3 = lineStyles.some((style) => {
        const paint = (style as { paint?: Record<string, unknown> }).paint ?? {};
        return paint['line-width'] === 3;
      });
      expect(hasWidth3).toBe(true);
    });

    it('uses a semi-transparent fill (opacity ~ 0.2) on at least one polygon fill style', () => {
      const fillStyles = MEASUREMENT_DRAW_STYLES.filter(
        (style) => (style as { type?: string }).type === 'fill',
      );
      const hasTransparentFill = fillStyles.some((style) => {
        const paint = (style as { paint?: Record<string, unknown> }).paint ?? {};
        const opacity = paint['fill-opacity'];
        return typeof opacity === 'number' && opacity <= 0.3 && opacity >= 0.1;
      });
      expect(hasTransparentFill).toBe(true);
    });

    it('does NOT use the canales blue #1971c2 anywhere (measurement must be visually distinct)', () => {
      for (const style of MEASUREMENT_DRAW_STYLES) {
        const paint = (style as { paint?: Record<string, unknown> }).paint ?? {};
        for (const value of Object.values(paint)) {
          expect(value).not.toBe('#1971c2');
        }
      }
    });
  });

  describe('createMeasurementDraw()', () => {
    it('returns a new MapboxDraw instance built with MEASUREMENT_DRAW_OPTIONS', () => {
      mapboxDrawConstructorSpy.mockClear();

      const instance = createMeasurementDraw();

      expect(instance).toBeDefined();
      expect(mapboxDrawConstructorSpy).toHaveBeenCalledTimes(1);
      expect(mapboxDrawConstructorSpy).toHaveBeenCalledWith(MEASUREMENT_DRAW_OPTIONS);
    });

    it('produces a FRESH instance on every call (dedicated draw, never shared)', () => {
      mapboxDrawConstructorSpy.mockClear();

      const a = createMeasurementDraw();
      const b = createMeasurementDraw();

      expect(a).not.toBe(b);
      expect(mapboxDrawConstructorSpy).toHaveBeenCalledTimes(2);
    });
  });
});
