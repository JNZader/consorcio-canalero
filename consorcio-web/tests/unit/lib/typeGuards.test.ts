/**
 * Phase 1 - Comprehensive mutation tests for typeGuards.ts
 * Targets: type checks, boundary validation, logic operators
 * Target kill rate: ≥80%
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
  isValidDashboardData,
  safeJsonParseValidated,
  assertValid,
  isValidSelectedImage,
  isValidImageComparison,
  type SelectedImageShape,
  type ImageComparisonShape,
} from '../../../src/lib/typeGuards';

describe('typeGuards - isValidUserRole()', () => {
  it('should accept valid roles', () => {
    expect(isValidUserRole('ciudadano')).toBe(true);
    expect(isValidUserRole('operador')).toBe(true);
    expect(isValidUserRole('admin')).toBe(true);
  });

  it('should reject invalid roles', () => {
    expect(isValidUserRole('super_admin')).toBe(false);
    expect(isValidUserRole('user')).toBe(false);
    expect(isValidUserRole('')).toBe(false);
  });

  it('should reject non-string inputs', () => {
    expect(isValidUserRole(123)).toBe(false);
    expect(isValidUserRole(null)).toBe(false);
    expect(isValidUserRole(undefined)).toBe(false);
    expect(isValidUserRole({})).toBe(false);
  });
});

describe('typeGuards - safeGetUserRole()', () => {
  it('should return role for valid input', () => {
    expect(safeGetUserRole('admin')).toBe('admin');
  });

  it('should return null for invalid input', () => {
    expect(safeGetUserRole('invalid')).toBeNull();
    expect(safeGetUserRole(123)).toBeNull();
  });
});

describe('typeGuards - isValidUsuario()', () => {
  const validUsuario = {
    id: 'user-123',
    email: 'user@example.com',
    rol: 'admin',
  };

  it('should accept valid usuario', () => {
    expect(isValidUsuario(validUsuario)).toBe(true);
  });

  it('should accept usuario with optional fields', () => {
    const withOptionals = {
      ...validUsuario,
      nombre: 'Juan',
      telefono: '+541234567890',
    };
    expect(isValidUsuario(withOptionals)).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidUsuario(null)).toBe(false);
    expect(isValidUsuario(undefined)).toBe(false);
  });

  it('should reject non-object types', () => {
    expect(isValidUsuario('string')).toBe(false);
    expect(isValidUsuario(123)).toBe(false);
  });

  it('should reject usuario with missing required id', () => {
    const { id, ...rest } = validUsuario;
    expect(isValidUsuario(rest)).toBe(false);
  });

  it('should reject usuario with empty id', () => {
    expect(isValidUsuario({ ...validUsuario, id: '' })).toBe(false);
  });

  it('should reject usuario with missing email', () => {
    const { email, ...rest } = validUsuario;
    expect(isValidUsuario(rest)).toBe(false);
  });

  it('should reject usuario with invalid role', () => {
    expect(isValidUsuario({ ...validUsuario, rol: 'superuser' })).toBe(false);
  });

  it('should reject usuario with non-string optional fields', () => {
    expect(isValidUsuario({ ...validUsuario, nombre: 123 })).toBe(false);
    expect(isValidUsuario({ ...validUsuario, telefono: {} })).toBe(false);
  });

  it('should allow null for optional fields', () => {
    expect(isValidUsuario({ ...validUsuario, nombre: null, telefono: null })).toBe(true);
  });

  // MUTATION CATCHING: Required field presence checks
  it('catches mutation: missing id check', () => {
    expect(isValidUsuario({ email: 'user@example.com', rol: 'admin' })).toBe(false);
    expect(isValidUsuario(validUsuario)).toBe(true);
  });

  it('catches mutation: id.length check', () => {
    expect(isValidUsuario({ ...validUsuario, id: '' })).toBe(false);
    expect(isValidUsuario({ ...validUsuario, id: 'a' })).toBe(true);
  });
});

describe('typeGuards - parseUsuario()', () => {
  it('should parse valid usuario', () => {
    const data = { id: 'user-123', email: 'user@example.com', rol: 'admin' };
    expect(parseUsuario(data)).toEqual(data);
  });

  it('should return null for invalid data', () => {
    expect(parseUsuario(null)).toBeNull();
    expect(parseUsuario('invalid')).toBeNull();
  });
});

describe('typeGuards - isValidLayerStyle()', () => {
  const validStyle = {
    color: '#FF0000',
    weight: 2,
    fillColor: '#0000FF',
    fillOpacity: 0.5,
  };

  it('should accept valid layer style', () => {
    expect(isValidLayerStyle(validStyle)).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidLayerStyle(null)).toBe(false);
    expect(isValidLayerStyle(undefined)).toBe(false);
  });

  it('should reject non-objects', () => {
    expect(isValidLayerStyle('string')).toBe(false);
  });

  it('should reject style missing required fields', () => {
    expect(isValidLayerStyle({ ...validStyle, color: undefined })).toBe(false);
    expect(isValidLayerStyle({ color: '#FF0000' })).toBe(false);
  });

  it('should reject fillOpacity outside [0, 1] range', () => {
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: -0.1 })).toBe(false);
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 1.5 })).toBe(false);
  });

  it('should accept fillOpacity at boundaries', () => {
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 0 })).toBe(true);
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 1 })).toBe(true);
  });

  // MUTATION CATCHING: Opacity boundary checks
  it('catches mutation: fillOpacity >= 0 boundary', () => {
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: -0.001 })).toBe(false);
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 0 })).toBe(true);
  });

  it('catches mutation: fillOpacity <= 1 boundary', () => {
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 1 })).toBe(true);
    expect(isValidLayerStyle({ ...validStyle, fillOpacity: 1.001 })).toBe(false);
  });
});

describe('typeGuards - parseLayerStyle()', () => {
  const defaultStyle = { color: '#3388ff', weight: 2, fillColor: '#3388ff', fillOpacity: 0.1 };

  it('should parse valid style object', () => {
    const style = {
      color: '#FF0000',
      weight: 2,
      fillColor: '#0000FF',
      fillOpacity: 0.5,
    };
    expect(parseLayerStyle(style)).toEqual(style);
  });

  it('should parse valid JSON string', () => {
    const style = {
      color: '#FF0000',
      weight: 2,
      fillColor: '#0000FF',
      fillOpacity: 0.5,
    };
    const result = parseLayerStyle(JSON.stringify(style));
    expect(result).toEqual(style);
  });

  it('should return default style for invalid JSON', () => {
    expect(parseLayerStyle('invalid json')).toEqual(defaultStyle);
  });

  it('should return default style for invalid object', () => {
    expect(parseLayerStyle({ invalid: true })).toEqual(defaultStyle);
  });

  it('should use custom default color', () => {
    const result = parseLayerStyle('invalid', '#FF0000');
    expect(result.color).toBe('#FF0000');
    expect(result.fillColor).toBe('#FF0000');
  });
});

describe('typeGuards - getStyleColor()', () => {
  it('should extract color from object', () => {
    const style = {
      color: '#FF0000',
      weight: 2,
      fillColor: '#0000FF',
      fillOpacity: 0.5,
    };
    expect(getStyleColor(style)).toBe('#FF0000');
  });

  it('should extract color from JSON string', () => {
    const style = {
      color: '#FF0000',
      weight: 2,
      fillColor: '#0000FF',
      fillOpacity: 0.5,
    };
    expect(getStyleColor(JSON.stringify(style))).toBe('#FF0000');
  });

  it('should return default color for invalid style', () => {
    expect(getStyleColor('invalid')).toBe('#3388ff');
  });

  it('should use custom default color', () => {
    expect(getStyleColor('invalid', '#FF0000')).toBe('#FF0000');
  });
});

describe('typeGuards - isValidGeometry()', () => {
  it('should accept Point geometry', () => {
    expect(isValidGeometry({ type: 'Point', coordinates: [0, 0] })).toBe(true);
  });

  it('should accept Polygon geometry', () => {
    expect(
      isValidGeometry({
        type: 'Polygon',
        coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]],
      })
    ).toBe(true);
  });

  it('should accept GeometryCollection', () => {
    expect(
      isValidGeometry({
        type: 'GeometryCollection',
        geometries: [{ type: 'Point', coordinates: [0, 0] }],
      })
    ).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidGeometry(null)).toBe(false);
    expect(isValidGeometry(undefined)).toBe(false);
  });

  it('should reject invalid geometry type', () => {
    expect(isValidGeometry({ type: 'InvalidType', coordinates: [] })).toBe(false);
  });

  it('should reject geometry without coordinates', () => {
    expect(isValidGeometry({ type: 'Point' })).toBe(false);
  });

  it('should reject GeometryCollection without geometries', () => {
    expect(isValidGeometry({ type: 'GeometryCollection' })).toBe(false);
  });

  // MUTATION CATCHING: Type-specific validation
  it('catches mutation: GeometryCollection type check', () => {
    expect(
      isValidGeometry({
        type: 'GeometryCollection',
        coordinates: [],
      })
    ).toBe(false);
    expect(
      isValidGeometry({
        type: 'GeometryCollection',
        geometries: [],
      })
    ).toBe(true);
  });
});

describe('typeGuards - isValidFeatureCollection()', () => {
  const validFC = {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [0, 0] },
        properties: {},
      },
    ],
  };

  it('should accept valid FeatureCollection', () => {
    expect(isValidFeatureCollection(validFC)).toBe(true);
  });

  it('should accept empty FeatureCollection', () => {
    expect(isValidFeatureCollection({ type: 'FeatureCollection', features: [] })).toBe(true);
  });

  it('should reject non-FeatureCollection type', () => {
    expect(isValidFeatureCollection({ type: 'Feature', features: [] })).toBe(false);
  });

  it('should reject missing features array', () => {
    expect(isValidFeatureCollection({ type: 'FeatureCollection' })).toBe(false);
  });

  it('should reject null/undefined', () => {
    expect(isValidFeatureCollection(null)).toBe(false);
    expect(isValidFeatureCollection(undefined)).toBe(false);
  });

  it('should reject feature with invalid geometry', () => {
    const invalidFC = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'InvalidType', coordinates: [] },
        },
      ],
    };
    expect(isValidFeatureCollection(invalidFC)).toBe(false);
  });

  it('should accept feature with null geometry', () => {
    const fcWithNullGeom = {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: null,
        },
      ],
    };
    expect(isValidFeatureCollection(fcWithNullGeom)).toBe(true);
  });
});

describe('typeGuards - parseFeatureCollection()', () => {
  const validFC = {
    type: 'FeatureCollection',
    features: [],
  };

  it('should parse valid FeatureCollection', () => {
    expect(parseFeatureCollection(validFC)).toEqual(validFC);
  });

  it('should return null for invalid data', () => {
    expect(parseFeatureCollection(null)).toBeNull();
    expect(parseFeatureCollection({ type: 'Feature' })).toBeNull();
  });
});

describe('typeGuards - isValidDashboardData()', () => {
  const validData = {
    summary: {
      area_total_ha: 1000,
      area_productiva_ha: 800,
      area_problematica_ha: 200,
      porcentaje_problematico: 20,
    },
    clasificacion: { class1: 100 },
    ranking_cuencas: [{ cuenca: 'Cuenca A', porcentaje_problematico: 15, area_anegada_ha: 50 }],
    alertas: [],
    periodo: { inicio: '2026-01-01', fin: '2026-03-09' },
  };

  it('should accept valid dashboard data', () => {
    expect(isValidDashboardData(validData)).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidDashboardData(null)).toBe(false);
    expect(isValidDashboardData(undefined)).toBe(false);
  });

  it('should reject missing summary', () => {
    const { summary, ...rest } = validData;
    expect(isValidDashboardData(rest)).toBe(false);
  });

  it('should reject summary with invalid types', () => {
    expect(
      isValidDashboardData({
        ...validData,
        summary: { ...validData.summary, area_total_ha: 'string' },
      })
    ).toBe(false);
  });

  it('should reject invalid ranking_cuencas', () => {
    expect(
      isValidDashboardData({
        ...validData,
        ranking_cuencas: 'not an array',
      })
    ).toBe(false);
  });

  it('should reject invalid periodo', () => {
    expect(
      isValidDashboardData({
        ...validData,
        periodo: { inicio: '2026-01-01' },
      })
    ).toBe(false);
  });
});

describe('typeGuards - safeJsonParseValidated()', () => {
  it('should parse and validate valid JSON', () => {
    const result = safeJsonParseValidated(
      '{"id":"123","email":"test@example.com","rol":"admin"}',
      isValidUsuario
    );
    expect(result?.id).toBe('123');
  });

  it('should return null for invalid JSON', () => {
    expect(safeJsonParseValidated('invalid json', isValidUsuario)).toBeNull();
  });

  it('should return null for invalid data', () => {
    expect(safeJsonParseValidated('{"invalid":true}', isValidUsuario)).toBeNull();
  });

  it('should return fallback when provided', () => {
    const fallback = { id: 'fallback', email: '', rol: 'ciudadano' as const };
    const result = safeJsonParseValidated('invalid', isValidUsuario, fallback);
    expect(result).toEqual(fallback);
  });
});

describe('typeGuards - assertValid()', () => {
  it('should not throw for valid data', () => {
    const validUsuario = { id: 'test', email: 'test@example.com', rol: 'admin' as const };
    expect(() => assertValid(validUsuario, isValidUsuario, 'Invalid usuario')).not.toThrow();
  });

  it('should throw for invalid data', () => {
    expect(() => assertValid({ invalid: true }, isValidUsuario, 'Invalid usuario')).toThrow(
      'Invalid usuario'
    );
  });

  it('should preserve type after assertion', () => {
    const data: unknown = { id: 'test', email: 'test@example.com', rol: 'admin' };
    assertValid(data, isValidUsuario, 'Invalid');
    // If we get here without error, type is narrowed
    expect(data.id).toBe('test');
  });
});

describe('typeGuards - isValidSelectedImage()', () => {
  const validImage: SelectedImageShape = {
    tile_url: 'https://earthengine.googleapis.com/tiles/{z}/{x}/{y}.png',
    target_date: '2026-03-09',
    sensor: 'Sentinel-2',
    visualization: 'NDVI',
    visualization_description: 'Normalized Difference Vegetation Index',
    collection: 'COPERNICUS/S2',
    images_count: 5,
    selected_at: '2026-03-09T10:30:00Z',
  };

  it('should accept valid selected image', () => {
    expect(isValidSelectedImage(validImage)).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidSelectedImage(null)).toBe(false);
    expect(isValidSelectedImage(undefined)).toBe(false);
  });

  it('should reject invalid sensor', () => {
    expect(isValidSelectedImage({ ...validImage, sensor: 'Landsat-8' as any })).toBe(false);
  });

  it('should reject negative images_count', () => {
    expect(isValidSelectedImage({ ...validImage, images_count: -1 })).toBe(false);
  });

  it('should reject non-HTTPS URLs', () => {
    expect(
      isValidSelectedImage({
        ...validImage,
        tile_url: 'http://example.com/{z}/{x}/{y}.png',
      })
    ).toBe(false);
  });

  it('should accept with flood_info', () => {
    expect(
      isValidSelectedImage({
        ...validImage,
        flood_info: {
          id: 'flood-1',
          name: 'Inundación A',
          description: 'Inundación en zona X',
          severity: 'high',
        },
      })
    ).toBe(true);
  });

  it('should reject invalid flood_info', () => {
    expect(
      isValidSelectedImage({
        ...validImage,
        flood_info: { id: 'flood-1' },
      })
    ).toBe(false);
  });
});

describe('typeGuards - isValidImageComparison()', () => {
  const validImage: SelectedImageShape = {
    tile_url: 'https://earthengine.googleapis.com/tiles/{z}/{x}/{y}.png',
    target_date: '2026-03-09',
    sensor: 'Sentinel-2',
    visualization: 'NDVI',
    visualization_description: 'NDVI',
    collection: 'COPERNICUS/S2',
    images_count: 5,
    selected_at: '2026-03-09T10:30:00Z',
  };

  const validComparison: ImageComparisonShape = {
    left: validImage,
    right: validImage,
    enabled: true,
  };

  it('should accept valid comparison', () => {
    expect(isValidImageComparison(validComparison)).toBe(true);
  });

  it('should reject null/undefined', () => {
    expect(isValidImageComparison(null)).toBe(false);
    expect(isValidImageComparison(undefined)).toBe(false);
  });

  it('should reject non-boolean enabled', () => {
    expect(isValidImageComparison({ ...validComparison, enabled: 'true' as any })).toBe(false);
  });

  it('should reject invalid left image', () => {
    expect(isValidImageComparison({ ...validComparison, left: { invalid: true } as any })).toBe(
      false
    );
  });

  it('should reject invalid right image', () => {
    expect(isValidImageComparison({ ...validComparison, right: { invalid: true } as any })).toBe(
      false
    );
  });

  it('should allow comparison with enabled=false', () => {
    expect(isValidImageComparison({ ...validComparison, enabled: false })).toBe(true);
  });
});
