// @ts-nocheck
import { describe, expect, it } from 'vitest';

import {
  assertValid,
  getStyleColor,
  isValidDashboardData,
  isValidFeatureCollection,
  isValidGeometry,
  isValidImageComparison,
  isValidLayerStyle,
  isValidSelectedImage,
  isValidUserRole,
  isValidUsuario,
  parseFeatureCollection,
  parseLayerStyle,
  parseUsuario,
  safeGetUserRole,
  safeJsonParseValidated,
} from '../../src/lib/typeGuards';

const validSelectedImage = {
  tile_url: 'https://earthengine.googleapis.com/map/abc/{z}/{x}/{y}',
  target_date: '2026-03-01',
  sensor: 'Sentinel-2' as const,
  visualization: 'rgb',
  visualization_description: 'RGB natural',
  collection: 'S2',
  images_count: 3,
  selected_at: '2026-03-01T10:00:00Z',
};

describe('typeGuards', () => {
  it('validates roles and usuario payloads', () => {
    expect(isValidUserRole('admin')).toBe(true);
    expect(isValidUserRole('guest')).toBe(false);
    expect(safeGetUserRole('operador')).toBe('operador');
    expect(safeGetUserRole('owner')).toBeNull();

    const user = { id: 'u1', email: 'a@b.com', rol: 'ciudadano', nombre: 'Ana' };
    expect(isValidUsuario(user)).toBe(true);
    expect(parseUsuario(user)).toEqual(user);
    expect(parseUsuario({ id: '', email: 'x', rol: 'admin' })).toBeNull();
  });

  it('parses layer styles from objects and strings with fallback', () => {
    const style = { color: '#111', weight: 3, fillColor: '#222', fillOpacity: 0.5 };

    expect(isValidLayerStyle(style)).toBe(true);
    expect(parseLayerStyle(style)).toEqual(style);
    expect(parseLayerStyle(JSON.stringify(style))).toEqual(style);
    expect(parseLayerStyle('{bad json}', '#0f0')).toEqual({
      color: '#0f0',
      weight: 2,
      fillColor: '#0f0',
      fillOpacity: 0.1,
    });
    expect(getStyleColor('not-json', '#f00')).toBe('#f00');
  });

  it('validates geometry and feature collections', () => {
    const point = { type: 'Point', coordinates: [1, 2] };
    const collection = {
      type: 'FeatureCollection',
      features: [{ type: 'Feature', geometry: point, properties: {} }],
    };

    expect(isValidGeometry(point)).toBe(true);
    expect(isValidGeometry({ type: 'GeometryCollection', geometries: [] })).toBe(true);
    expect(isValidGeometry({ type: 'Invalid', coordinates: [] })).toBe(false);

    expect(isValidFeatureCollection(collection)).toBe(true);
    expect(parseFeatureCollection(collection)?.type).toBe('FeatureCollection');
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: [{}] })).toBe(false);
  });

  it('validates dashboard shape and generic parse/assert helpers', () => {
    const dashboard = {
      summary: {
        area_total_ha: 100,
        area_productiva_ha: 80,
        area_problematica_ha: 20,
        porcentaje_problematico: 20,
      },
      clasificacion: {},
      ranking_cuencas: [],
      alertas: [],
      periodo: { inicio: '2026-01-01', fin: '2026-01-31' },
    };

    expect(isValidDashboardData(dashboard)).toBe(true);
    expect(isValidDashboardData({ ...dashboard, periodo: { inicio: 1, fin: 'x' } })).toBe(false);

    const parsed = safeJsonParseValidated('{"ok":true}', (v): v is { ok: boolean } => {
      return typeof v === 'object' && v !== null && 'ok' in v;
    });
    expect(parsed).toEqual({ ok: true });
    expect(safeJsonParseValidated('bad', (v): v is string => typeof v === 'string', 'fallback')).toBe('fallback');

    expect(() => assertValid('x', (v): v is string => typeof v === 'string', 'bad')).not.toThrow();
    expect(() => assertValid(1, (v): v is string => typeof v === 'string', 'bad')).toThrow('bad');
  });

  it('validates selected image and comparison payloads from localStorage', () => {
    expect(isValidSelectedImage(validSelectedImage)).toBe(true);
    expect(isValidSelectedImage({ ...validSelectedImage, sensor: 'Landsat' })).toBe(false);
    expect(isValidSelectedImage({ ...validSelectedImage, images_count: -1 })).toBe(false);
    expect(
      isValidSelectedImage({ ...validSelectedImage, tile_url: 'https://maps.googleapis.com/tile/{z}/{x}/{y}' })
    ).toBe(false);
    expect(isValidSelectedImage({ ...validSelectedImage, flood_info: { id: 1 } })).toBe(false);

    const comparison = {
      left: validSelectedImage,
      right: { ...validSelectedImage, sensor: 'Sentinel-1' as const },
      enabled: true,
    };

    expect(isValidImageComparison(comparison)).toBe(true);
    expect(isValidImageComparison({ ...comparison, enabled: 'yes' })).toBe(false);
    expect(isValidImageComparison({ ...comparison, right: { foo: 'bar' } })).toBe(false);
  });
});
