import { describe, expect, it } from 'vitest';

import {
  assertValid,
  getStyleColor,
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
} from '../../../src/lib/typeGuards';

const validUsuario = {
  id: 'user-1',
  email: 'user@example.com',
  rol: 'admin',
  nombre: 'Jane Doe',
};

const validLayerStyle = {
  color: '#ff0000',
  weight: 2,
  fillColor: '#00ff00',
  fillOpacity: 0.5,
};

const validPoint = { type: 'Point', coordinates: [0, 0] };
const validFeatureCollection = {
  type: 'FeatureCollection',
  features: [{ type: 'Feature', geometry: validPoint, properties: {} }],
};

const validSelectedImage = {
  tile_url: 'https://example.com/tiles/{z}/{x}/{y}',
  target_date: '2026-04-01',
  sensor: 'Sentinel-2',
  visualization: 'ndvi',
  visualization_description: 'Indice de vegetacion',
  collection: 'test-collection',
  images_count: 3,
  selected_at: '2026-04-01T12:00:00Z',
};

describe('typeGuards', () => {
  describe('user and usuario guards', () => {
    it('validates roles and safely extracts them', () => {
      expect(isValidUserRole('admin')).toBe(true);
      expect(isValidUserRole('Admin')).toBe(false);
      expect(isValidUserRole('superuser')).toBe(false);
      expect(safeGetUserRole('operador')).toBe('operador');
      expect(safeGetUserRole(undefined)).toBeNull();
      expect(safeGetUserRole('invalid')).toBeNull();
    });

    it('validates usuarios including optional field types', () => {
      expect(isValidUsuario(validUsuario)).toBe(true);
      expect(parseUsuario(validUsuario)).toEqual(validUsuario);
      expect(
        isValidUsuario({ ...validUsuario, id: '' })
      ).toBe(false);
      expect(
        isValidUsuario({ ...validUsuario, email: 123 })
      ).toBe(false);
      expect(
        isValidUsuario({ ...validUsuario, nombre: null, telefono: undefined })
      ).toBe(true);
      expect(
        isValidUsuario({ ...validUsuario, nombre: 42 })
      ).toBe(false);
      expect(parseUsuario({ id: 'only-id' })).toBeNull();
    });
  });

  describe('layer styles', () => {
    it('validates and parses layer styles with defaults', () => {
      expect(isValidLayerStyle(validLayerStyle)).toBe(true);
      expect(isValidLayerStyle({ ...validLayerStyle, fillOpacity: 1.1 })).toBe(false);
      expect(isValidLayerStyle({ ...validLayerStyle, fillOpacity: -0.1 })).toBe(false);
      expect(parseLayerStyle(validLayerStyle)).toEqual(validLayerStyle);
      expect(parseLayerStyle(JSON.stringify(validLayerStyle))).toEqual(validLayerStyle);
      expect(parseLayerStyle('{invalid}', 'purple')).toEqual({
        color: 'purple',
        weight: 2,
        fillColor: 'purple',
        fillOpacity: 0.1,
      });
      expect(getStyleColor(validLayerStyle)).toBe('#ff0000');
      expect(getStyleColor('{invalid}', 'orange')).toBe('orange');
    });
  });

  describe('geojson guards', () => {
    it('validates geometries including geometry collections', () => {
      expect(isValidGeometry(validPoint)).toBe(true);
      expect(
        isValidGeometry({ type: 'GeometryCollection', geometries: [validPoint] })
      ).toBe(true);
      expect(isValidGeometry({ type: 'Point' })).toBe(false);
      expect(
        isValidGeometry({ type: 'GeometryCollection', coordinates: [[0, 0]] })
      ).toBe(false);
      expect(isValidGeometry({ coordinates: [0, 0] })).toBe(false);
    });

    it('validates feature collections and parsers', () => {
      expect(isValidFeatureCollection(validFeatureCollection)).toBe(true);
      expect(parseFeatureCollection(validFeatureCollection)).toEqual(validFeatureCollection);
      expect(
        isValidFeatureCollection({ type: 'FeatureCollection', features: [{ type: 'Feature', geometry: null }] })
      ).toBe(true);
      expect(
        isValidFeatureCollection({ type: 'FeatureCollection', features: [{ type: 'Geometry', geometry: validPoint }] })
      ).toBe(false);
      expect(
        isValidFeatureCollection({ type: 'FeatureCollection' })
      ).toBe(false);
      expect(parseFeatureCollection({ type: 'Feature' })).toBeNull();
    });
  });

  describe('generic helpers', () => {
    it('parses validated json with optional fallback', () => {
      const isNumber = (value: unknown): value is number => typeof value === 'number';

      expect(safeJsonParseValidated('123', isNumber)).toBe(123);
      expect(safeJsonParseValidated('"abc"', isNumber)).toBeNull();
      expect(safeJsonParseValidated('{invalid}', isNumber, 42)).toBe(42);
    });

    it('asserts valid values and throws custom errors otherwise', () => {
      const isString = (value: unknown): value is string => typeof value === 'string';

      expect(() => assertValid('hello', isString, 'Must be string')).not.toThrow();
      expect(() => assertValid(123, isString, 'Must be string')).toThrow('Must be string');
    });
  });

  describe('localStorage shape guards', () => {
    it('validates selected images including URL, sensor and flood info rules', () => {
      expect(isValidSelectedImage(validSelectedImage)).toBe(true);
      expect(
        isValidSelectedImage({
          ...validSelectedImage,
          flood_info: {
            id: 'flood-1',
            name: 'Evento',
            description: 'Descripcion',
            severity: 'high',
          },
        })
      ).toBe(true);
      expect(isValidSelectedImage({ ...validSelectedImage, tile_url: 'http://example.com/{z}/{x}/{y}' })).toBe(false);
      expect(isValidSelectedImage({ ...validSelectedImage, tile_url: 'https://foo.googleapis.com/{z}/{x}/{y}' })).toBe(false);
      expect(isValidSelectedImage({ ...validSelectedImage, sensor: 'Landsat-8' })).toBe(false);
      expect(isValidSelectedImage({ ...validSelectedImage, images_count: -1 })).toBe(false);
      expect(isValidSelectedImage({ ...validSelectedImage, flood_info: { id: '1' } })).toBe(false);
    });

    it('validates image comparison payloads', () => {
      expect(
        isValidImageComparison({
          left: validSelectedImage,
          right: { ...validSelectedImage, sensor: 'Sentinel-1' },
          enabled: true,
        })
      ).toBe(true);
      expect(
        isValidImageComparison({
          left: validSelectedImage,
          right: validSelectedImage,
          enabled: 'true',
        })
      ).toBe(false);
      expect(
        isValidImageComparison({ left: { invalid: true }, right: validSelectedImage, enabled: true })
      ).toBe(false);
    });
  });
});
