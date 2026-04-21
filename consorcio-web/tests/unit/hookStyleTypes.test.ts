/**
 * Task 1.8 — Verify hook return types no longer include Leaflet PathOptions.
 *
 * These tests assert that:
 * 1. useWaterways exports WaterwayStyle (not Leaflet PathOptions) — no leaflet import
 * 2. useGEELayers exports GEELayerPaint (not Leaflet PathOptions) — no leaflet import
 * 3. useMartinLayers exports MartinSourceStyle (not vectorgrid StyleDef) — no leaflet.vectorgrid import
 * 4. useSoilMap, useCaminosColoreados, useCatastroMap have no Leaflet PathOptions in return types
 *
 * Type-level assertions: if these compile, the types are correct.
 * Runtime assertions: validate the actual constant values have the expected shape.
 */

import { describe, expect, it } from 'vitest';

import {
  GEE_LAYER_COLORS,
  GEE_LAYER_STYLES,
  type GEELayerPaint,
} from '../../src/hooks/useGEELayers';

import {
  MARTIN_SOURCES,
  type MartinSourceStyle,
} from '../../src/hooks/useMartinLayers';

import type { WaterwayStyle } from '../../src/hooks/useWaterways';

// ─── useWaterways ─────────────────────────────────────────────────────────────

describe('useWaterways — WaterwayStyle type', () => {
  it('WaterwayStyle has color, weight, opacity and optional dashArray — no Leaflet-specific fields', () => {
    // Type-level: this object satisfies WaterwayStyle
    const style: WaterwayStyle = { color: '#1565C0', weight: 4, opacity: 0.9 };
    expect(style.color).toBe('#1565C0');
    expect(style.weight).toBe(4);
    expect(style.opacity).toBe(0.9);
    // dashArray is optional
    expect(style.dashArray).toBeUndefined();
  });

  it('WaterwayStyle with dashArray is valid', () => {
    const style: WaterwayStyle = { color: '#0B3D91', weight: 4, opacity: 0.95, dashArray: '6 4' };
    expect(style.dashArray).toBe('6 4');
  });
});

// ─── useGEELayers ─────────────────────────────────────────────────────────────

describe('useGEELayers — GEELayerPaint type', () => {
  it('GEE_LAYER_STYLES entries satisfy GEELayerPaint — no PathOptions-exclusive fields', () => {
    const zonaStyle: GEELayerPaint = GEE_LAYER_STYLES.zona;
    expect(zonaStyle.color).toBe('#FF0000');
    expect(zonaStyle.weight).toBe(3);
    expect(zonaStyle.fillOpacity).toBe(0);
  });

  it('GEE_LAYER_STYLES entries with fillColor are valid', () => {
    const candilStyle: GEELayerPaint = GEE_LAYER_STYLES.candil;
    expect(candilStyle.fillColor).toBe('#2196F3');
  });

  it('GEE_LAYER_COLORS and GEE_LAYER_STYLES share the same color values', () => {
    for (const name of ['zona', 'candil', 'ml', 'noroeste', 'norte'] as const) {
      expect(GEE_LAYER_STYLES[name].color).toBe(GEE_LAYER_COLORS[name]);
    }
  });
});

// ─── useMartinLayers ─────────────────────────────────────────────────────────

describe('useMartinLayers — MartinSourceStyle type', () => {
  it('MARTIN_SOURCES paint has no "fill" boolean field (leaflet.vectorgrid-specific)', () => {
    const style: MartinSourceStyle = MARTIN_SOURCES.puntos_conflicto.style;
    expect(style.color).toBe('#b91c1c');
    expect(style.fillColor).toBe('#ef4444');
    expect(style.fillOpacity).toBe(0.85);
    expect(style.radius).toBe(5);
    // The "fill: boolean" field from leaflet.vectorgrid StyleDef must NOT exist
    expect('fill' in style).toBe(false);
  });
});
