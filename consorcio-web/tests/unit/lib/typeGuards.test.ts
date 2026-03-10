/**
 * Mutation tests for src/lib/typeGuards.ts
 * Tests type validation functions for runtime type checking
 */

import { describe, it, expect } from 'vitest';
import {
  isValidUserRole,
  safeGetUserRole,
  isValidUsuario,
  parseUsuario,
  isValidLayerStyle,
  parseLayerStyle,
  getStyleColor,
  isValidGeometry,
  isValidFeatureCollection,
  parseFeatureCollection,
  safeJsonParseValidated,
  assertValid,
  isValidSelectedImage,
  isValidImageComparison,
} from '../../../src/lib/typeGuards';
import {
  userRoleTestCases,
  usuarioTestCases,
  layerStyleTestCases,
  geometryTestCases,
  selectedImageTestCases,
} from './setup';

describe('typeGuards', () => {
  describe('isValidUserRole', () => {
    it.each(userRoleTestCases.valid)('should accept valid role: %s', (role) => {
      expect(isValidUserRole(role)).toBe(true);
    });

    it.each(userRoleTestCases.invalid)('should reject invalid role: %s', (role) => {
      expect(isValidUserRole(role)).toBe(false);
    });

    it('should catch mutation on includes check', () => {
      expect(isValidUserRole('ciudadano')).toBe(true);
      expect(isValidUserRole('superuser')).toBe(false);
    });

    it('should be case-sensitive', () => {
      expect(isValidUserRole('Admin')).toBe(false);
      expect(isValidUserRole('ADMIN')).toBe(false);
      expect(isValidUserRole('admin')).toBe(true);
    });
  });

  describe('safeGetUserRole', () => {
    it('should return role for valid input', () => {
      expect(safeGetUserRole('admin')).toBe('admin');
      expect(safeGetUserRole('operador')).toBe('operador');
    });

    it('should return null for invalid input', () => {
      expect(safeGetUserRole('invalid')).toBeNull();
      expect(safeGetUserRole('Admin')).toBeNull();
    });

    it('should catch mutation on null vs undefined', () => {
      expect(safeGetUserRole(undefined)).toBeNull();
      expect(safeGetUserRole(null)).toBeNull();
    });
  });

  describe('isValidUsuario', () => {
    it.each(usuarioTestCases.valid)('should accept valid usuario: %s', (usuario) => {
      expect(isValidUsuario(usuario)).toBe(true);
    });

    it.each(usuarioTestCases.invalid)('should reject invalid usuario: %s', (usuario) => {
      expect(isValidUsuario(usuario)).toBe(false);
    });

    it('should require non-empty id string', () => {
      const usuario = {
        id: '',
        email: 'user@example.com',
        rol: 'ciudadano',
      };
      expect(isValidUsuario(usuario)).toBe(false);
    });

    it('should allow null/undefined optional fields', () => {
      const usuario = {
        id: 'user-1',
        email: 'user@example.com',
        rol: 'ciudadano',
        nombre: null,
        telefono: undefined,
      };
      expect(isValidUsuario(usuario)).toBe(true);
    });

    it('should reject invalid types for optional fields', () => {
      const usuario = {
        id: 'user-1',
        email: 'user@example.com',
        rol: 'ciudadano',
        nombre: 123,
      };
      expect(isValidUsuario(usuario)).toBe(false);
    });

    it('should catch mutation on field type checks', () => {
      const validUsuario = {
        id: 'user-1',
        email: 'user@example.com',
        rol: 'admin',
      };
      expect(isValidUsuario(validUsuario)).toBe(true);

      const invalidEmail = {
        id: 'user-1',
        email: 123,
        rol: 'admin',
      };
      expect(isValidUsuario(invalidEmail)).toBe(false);
    });

    it('should validate all required fields', () => {
      const usuario = {
        id: 'user-1',
        email: 'user@example.com',
        rol: 'invalid-role',
      };
      expect(isValidUsuario(usuario)).toBe(false);
    });
  });

  describe('parseUsuario', () => {
    it('should return usuario for valid data', () => {
      const usuario = {
        id: 'user-1',
        email: 'user@example.com',
        rol: 'operador',
      };
      expect(parseUsuario(usuario)).toEqual(usuario);
    });

    it('should return null for invalid data', () => {
      expect(parseUsuario({ id: 'user-1' })).toBeNull();
      expect(parseUsuario(null)).toBeNull();
    });
  });

  describe('isValidLayerStyle', () => {
    it.each(layerStyleTestCases.valid)(
      'should accept valid layer style: %s',
      (style) => {
        expect(isValidLayerStyle(style)).toBe(true);
      }
    );

    it.each(layerStyleTestCases.invalid)(
      'should reject invalid layer style: %s',
      (style) => {
        expect(isValidLayerStyle(style)).toBe(false);
      }
    );

    it('should require all four properties', () => {
      const incomplete = {
        color: '#fff',
        weight: 2,
      };
      expect(isValidLayerStyle(incomplete)).toBe(false);
    });

    it('should validate fillOpacity range (0-1)', () => {
      const tooHigh = {
        color: '#fff',
        weight: 2,
        fillColor: '#fff',
        fillOpacity: 1.1,
      };
      expect(isValidLayerStyle(tooHigh)).toBe(false);

      const tooLow = {
        color: '#fff',
        weight: 2,
        fillColor: '#fff',
        fillOpacity: -0.1,
      };
      expect(isValidLayerStyle(tooLow)).toBe(false);

      const valid = {
        color: '#fff',
        weight: 2,
        fillColor: '#fff',
        fillOpacity: 0.5,
      };
      expect(isValidLayerStyle(valid)).toBe(true);
    });

    it('should catch mutation on opacity boundary checks', () => {
      const atBoundary1 = {
        color: '#fff',
        weight: 2,
        fillColor: '#fff',
        fillOpacity: 0,
      };
      expect(isValidLayerStyle(atBoundary1)).toBe(true);

      const atBoundary2 = {
        color: '#fff',
        weight: 2,
        fillColor: '#fff',
        fillOpacity: 1,
      };
      expect(isValidLayerStyle(atBoundary2)).toBe(true);
    });
  });

  describe('parseLayerStyle', () => {
    it('should parse valid JSON string', () => {
      const json = '{"color":"#ff0000","weight":2,"fillColor":"#00ff00","fillOpacity":0.5}';
      const result = parseLayerStyle(json);

      expect(result.color).toBe('#ff0000');
      expect(result.fillOpacity).toBe(0.5);
    });

    it('should return default style for invalid JSON', () => {
      const result = parseLayerStyle('{invalid}');

      expect(result.color).toBe('#3388ff');
      expect(result.weight).toBe(2);
    });

    it('should accept object directly', () => {
      const style = {
        color: 'red',
        weight: 3,
        fillColor: 'blue',
        fillOpacity: 1,
      };
      const result = parseLayerStyle(style);

      expect(result.color).toBe('red');
    });

    it('should use custom default color', () => {
      const result = parseLayerStyle('{invalid}', 'purple');

      expect(result.color).toBe('purple');
      expect(result.fillColor).toBe('purple');
    });

    it('should return default for invalid object', () => {
      const result = parseLayerStyle({ invalid: true });

      expect(result.color).toBe('#3388ff');
    });
  });

  describe('getStyleColor', () => {
    it('should extract color from style string', () => {
      const json = '{"color":"red","weight":2,"fillColor":"blue","fillOpacity":0.5}';
      const result = getStyleColor(json);

      expect(result).toBe('red');
    });

    it('should extract color from style object', () => {
      const style = {
        color: 'green',
        weight: 2,
        fillColor: 'yellow',
        fillOpacity: 0.5,
      };
      const result = getStyleColor(style);

      expect(result).toBe('green');
    });

    it('should use default color for invalid input', () => {
      const result = getStyleColor('{invalid}');

      expect(result).toBe('#3388ff');
    });

    it('should use custom default color', () => {
      const result = getStyleColor('{invalid}', 'orange');

      expect(result).toBe('orange');
    });
  });

  describe('isValidGeometry', () => {
    it.each(Object.entries(geometryTestCases.valid))(
      'should accept valid %s geometry',
      (_, geometry) => {
        expect(isValidGeometry(geometry)).toBe(true);
      }
    );

    it.each(geometryTestCases.invalid)('should reject invalid geometry: %s', (geometry) => {
      expect(isValidGeometry(geometry)).toBe(false);
    });

    it('should validate required type field', () => {
      const noType = { coordinates: [[0, 0]] };
      expect(isValidGeometry(noType)).toBe(false);
    });

    it('should validate coordinates for non-GeometryCollection', () => {
      const noCoordinates = { type: 'Point' };
      expect(isValidGeometry(noCoordinates)).toBe(false);
    });

    it('should validate geometries for GeometryCollection', () => {
      const valid = {
        type: 'GeometryCollection',
        geometries: [{ type: 'Point', coordinates: [0, 0] }],
      };
      expect(isValidGeometry(valid)).toBe(true);

      const invalid = {
        type: 'GeometryCollection',
        coordinates: [[0, 0]],
      };
      expect(isValidGeometry(invalid)).toBe(false);
    });

    it('should catch mutation on GeometryCollection check', () => {
      const geomCollection = {
        type: 'GeometryCollection',
        geometries: [{ type: 'Point', coordinates: [0, 0] }],
      };
      expect(isValidGeometry(geomCollection)).toBe(true);

      const point = {
        type: 'Point',
        coordinates: [0, 0],
      };
      expect(isValidGeometry(point)).toBe(true);
    });
  });

  describe('isValidFeatureCollection', () => {
    it('should accept valid FeatureCollection', () => {
      const fc = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
            properties: {},
          },
        ],
      };
      expect(isValidFeatureCollection(fc)).toBe(true);
    });

    it('should reject if type is not FeatureCollection', () => {
      const fc = {
        type: 'Feature',
        features: [],
      };
      expect(isValidFeatureCollection(fc)).toBe(false);
    });

    it('should require features array', () => {
      const noFeatures = {
        type: 'FeatureCollection',
      };
      expect(isValidFeatureCollection(noFeatures)).toBe(false);
    });

    it('should validate each feature', () => {
      const invalidFeature = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: null,
            properties: {},
          },
          {
            type: 'Feature',
            // Missing geometry
            properties: {},
          },
        ],
      };
      // Should handle mixed valid/invalid
      expect(isValidFeatureCollection(invalidFeature)).toBe(false);
    });

    it('should allow null geometry', () => {
      const fc = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: null,
            properties: {},
          },
        ],
      };
      expect(isValidFeatureCollection(fc)).toBe(true);
    });

    it('should catch mutation on feature type check', () => {
      const validFc = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [0, 0] },
          },
        ],
      };
      expect(isValidFeatureCollection(validFc)).toBe(true);

      const wrongFeatureType = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Geometry',
            geometry: { type: 'Point', coordinates: [0, 0] },
          },
        ],
      };
      expect(isValidFeatureCollection(wrongFeatureType)).toBe(false);
    });
  });

  describe('parseFeatureCollection', () => {
    it('should return valid FeatureCollection', () => {
      const fc = {
        type: 'FeatureCollection',
        features: [],
      };
      expect(parseFeatureCollection(fc)).toEqual(fc);
    });

    it('should return null for invalid data', () => {
      expect(parseFeatureCollection(null)).toBeNull();
      expect(parseFeatureCollection({ type: 'Feature' })).toBeNull();
    });
  });

  describe('safeJsonParseValidated', () => {
    const numberValidator = (value: unknown): value is number => typeof value === 'number';

    it('should parse and validate', () => {
      const result = safeJsonParseValidated('123', numberValidator);
      expect(result).toBe(123);
    });

    it('should return null for invalid JSON', () => {
      const result = safeJsonParseValidated('{invalid}', numberValidator);
      expect(result).toBeNull();
    });

    it('should return null for validation failure', () => {
      const result = safeJsonParseValidated('"string"', numberValidator);
      expect(result).toBeNull();
    });

    it('should use fallback value', () => {
      const result = safeJsonParseValidated('{invalid}', numberValidator, 42);
      expect(result).toBe(42);
    });
  });

  describe('assertValid', () => {
    const validator = (value: unknown): value is string => typeof value === 'string';

    it('should not throw for valid value', () => {
      expect(() => {
        assertValid('hello', validator, 'Must be string');
      }).not.toThrow();
    });

    it('should throw for invalid value', () => {
      expect(() => {
        assertValid(123, validator, 'Must be string');
      }).toThrow('Must be string');
    });

    it('should include custom error message', () => {
      expect(() => {
        assertValid(null, validator, 'Custom error message');
      }).toThrow('Custom error message');
    });
  });

  describe('isValidSelectedImage', () => {
    it('should accept valid selected image', () => {
      expect(isValidSelectedImage(selectedImageTestCases.valid.basic)).toBe(true);
    });

    it('should accept selected image with flood info', () => {
      expect(isValidSelectedImage(selectedImageTestCases.valid.withFloodInfo)).toBe(true);
    });

    it('should require all mandatory fields', () => {
      const incomplete = {
        tile_url: 'https://example.com/{z}/{x}/{y}',
        // Missing other fields
      };
      expect(isValidSelectedImage(incomplete)).toBe(false);
    });

    it('should validate tile_url format', () => {
      const http = {
        ...selectedImageTestCases.valid.basic,
        tile_url: 'http://example.com/{z}/{x}/{y}', // HTTP not HTTPS
      };
      expect(isValidSelectedImage(http)).toBe(false);
    });

    it('should validate sensor values', () => {
      const badSensor = {
        ...selectedImageTestCases.valid.basic,
        sensor: 'Landsat-8',
      };
      expect(isValidSelectedImage(badSensor)).toBe(false);
    });

    it('should validate images_count is non-negative', () => {
      const negative = {
        ...selectedImageTestCases.valid.basic,
        images_count: -1,
      };
      expect(isValidSelectedImage(negative)).toBe(false);
    });

    it('should validate tile_url is HTTPS', () => {
      const invalidUrl = {
        ...selectedImageTestCases.valid.basic,
        tile_url: 'ftp://example.com/{z}/{x}/{y}',
      };
      expect(isValidSelectedImage(invalidUrl)).toBe(false);
    });
  });

  describe('isValidImageComparison', () => {
    it('should accept valid image comparison', () => {
      const comparison = {
        left: selectedImageTestCases.valid.basic,
        right: selectedImageTestCases.valid.basic,
        enabled: true,
      };
      expect(isValidImageComparison(comparison)).toBe(true);
    });

    it('should validate enabled is boolean', () => {
      const invalid = {
        left: selectedImageTestCases.valid.basic,
        right: selectedImageTestCases.valid.basic,
        enabled: 'true',
      };
      expect(isValidImageComparison(invalid)).toBe(false);
    });

    it('should validate both left and right images', () => {
      const invalidLeft = {
        left: { invalid: true },
        right: selectedImageTestCases.valid.basic,
        enabled: true,
      };
      expect(isValidImageComparison(invalidLeft)).toBe(false);
    });
  });
});
