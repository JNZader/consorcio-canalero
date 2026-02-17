/**
 * Runtime type guards and validators for the Consorcio Canalero application.
 * These functions validate data at runtime, especially for API responses
 * and JSON parsing where TypeScript assertions alone are insufficient.
 *
 * Pattern: Each type guard follows the signature `function isFoo(x: unknown): x is Foo`
 * This allows TypeScript to narrow the type in conditional blocks.
 */

import type { FeatureCollection, Geometry } from 'geojson';
import type {
  LayerStyle,
  Usuario,
} from '../types';

// ===========================================
// USER / AUTH TYPE GUARDS
// ===========================================

/** Valid user roles in the system */
const VALID_USER_ROLES = ['ciudadano', 'operador', 'admin'] as const;
export type UserRole = (typeof VALID_USER_ROLES)[number];

/** Allowed hostnames for Google Earth Engine tile URLs */
const ALLOWED_EARTH_ENGINE_HOSTNAMES = ['earthengine.googleapis.com'] as const;

/**
 * Validates if a value is a valid UserRole.
 * Use this when receiving role data from API or storage.
 */
export function isValidUserRole(value: unknown): value is UserRole {
  return typeof value === 'string' && VALID_USER_ROLES.includes(value as UserRole);
}

/**
 * Safely extracts user role with runtime validation.
 * Returns the role if valid, null otherwise.
 */
export function safeGetUserRole(value: unknown): UserRole | null {
  return isValidUserRole(value) ? value : null;
}

/**
 * Validates if an object is a valid Usuario (user profile).
 * Checks for required fields and their types.
 */
export function isValidUsuario(value: unknown): value is Usuario {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  // Required fields
  if (typeof obj.id !== 'string' || obj.id.length === 0) {
    return false;
  }
  if (typeof obj.email !== 'string') {
    return false;
  }
  if (!isValidUserRole(obj.rol)) {
    return false;
  }

  // Optional fields - validate if present (allow null or string)
  if (obj.nombre !== undefined && obj.nombre !== null && typeof obj.nombre !== 'string') {
    return false;
  }
  if (obj.telefono !== undefined && obj.telefono !== null && typeof obj.telefono !== 'string') {
    return false;
  }

  return true;
}

/**
 * Safely parses an API response as Usuario.
 * Returns null if validation fails.
 */
export function parseUsuario(data: unknown): Usuario | null {
  return isValidUsuario(data) ? data : null;
}

// ===========================================
// LAYER STYLE TYPE GUARDS
// ===========================================

/**
 * Validates if an object is a valid LayerStyle.
 */
export function isValidLayerStyle(value: unknown): value is LayerStyle {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  return (
    typeof obj.color === 'string' &&
    typeof obj.weight === 'number' &&
    typeof obj.fillColor === 'string' &&
    typeof obj.fillOpacity === 'number' &&
    obj.fillOpacity >= 0 &&
    obj.fillOpacity <= 1
  );
}

/**
 * Safely parses layer style from JSON string or object.
 * Returns a default style if parsing fails.
 */
export function parseLayerStyle(
  value: string | LayerStyle | unknown,
  defaultColor = '#3388ff'
): LayerStyle {
  const defaultStyle: LayerStyle = {
    color: defaultColor,
    weight: 2,
    fillColor: defaultColor,
    fillOpacity: 0.1,
  };

  if (typeof value === 'string') {
    try {
      const parsed = JSON.parse(value);
      return isValidLayerStyle(parsed) ? parsed : defaultStyle;
    } catch {
      return defaultStyle;
    }
  }

  return isValidLayerStyle(value) ? value : defaultStyle;
}

/**
 * Extracts color from layer style with fallback.
 */
export function getStyleColor(
  estilo: string | LayerStyle | unknown,
  defaultColor = '#3388ff'
): string {
  const style = parseLayerStyle(estilo, defaultColor);
  return style.color;
}

// ===========================================
// GEOJSON TYPE GUARDS
// ===========================================

/** Valid GeoJSON geometry types */
const VALID_GEOMETRY_TYPES = [
  'Point',
  'MultiPoint',
  'LineString',
  'MultiLineString',
  'Polygon',
  'MultiPolygon',
  'GeometryCollection',
] as const;

/**
 * Validates if a value is a valid GeoJSON Geometry.
 */
export function isValidGeometry(value: unknown): value is Geometry {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  if (typeof obj.type !== 'string') {
    return false;
  }

  if (!VALID_GEOMETRY_TYPES.includes(obj.type as (typeof VALID_GEOMETRY_TYPES)[number])) {
    return false;
  }

  // GeometryCollection has 'geometries' instead of 'coordinates'
  if (obj.type === 'GeometryCollection') {
    return Array.isArray(obj.geometries);
  }

  return Array.isArray(obj.coordinates);
}

/**
 * Validates if a value is a valid GeoJSON FeatureCollection.
 */
export function isValidFeatureCollection(value: unknown): value is FeatureCollection {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  if (obj.type !== 'FeatureCollection') {
    return false;
  }

  if (!Array.isArray(obj.features)) {
    return false;
  }

  // Validate each feature has at minimum type and geometry
  return obj.features.every((feature) => {
    if (feature === null || typeof feature !== 'object') {
      return false;
    }
    const f = feature as Record<string, unknown>;
    return f.type === 'Feature' && (f.geometry === null || isValidGeometry(f.geometry));
  });
}

/**
 * Safely parses an API response as FeatureCollection.
 * Returns null if validation fails.
 */
export function parseFeatureCollection(data: unknown): FeatureCollection | null {
  return isValidFeatureCollection(data) ? data : null;
}

// ===========================================
// MONITORING DASHBOARD TYPE GUARDS
// ===========================================

/**
 * Validates dashboard data structure from monitoring API.
 */
export function isValidDashboardData(value: unknown): value is {
  summary: {
    area_total_ha: number;
    area_productiva_ha: number;
    area_problematica_ha: number;
    porcentaje_problematico: number;
  };
  clasificacion: Record<string, unknown>;
  ranking_cuencas: Array<{
    cuenca: string;
    porcentaje_problematico: number;
    area_anegada_ha: number;
  }>;
  alertas: unknown[];
  periodo: { inicio: string; fin: string };
} {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  // Validate summary
  if (!obj.summary || typeof obj.summary !== 'object') {
    return false;
  }

  const summary = obj.summary as Record<string, unknown>;
  if (
    typeof summary.area_total_ha !== 'number' ||
    typeof summary.area_productiva_ha !== 'number' ||
    typeof summary.area_problematica_ha !== 'number' ||
    typeof summary.porcentaje_problematico !== 'number'
  ) {
    return false;
  }

  // Validate other required fields exist
  if (typeof obj.clasificacion !== 'object' || obj.clasificacion === null) {
    return false;
  }

  if (!Array.isArray(obj.ranking_cuencas)) {
    return false;
  }

  if (!Array.isArray(obj.alertas)) {
    return false;
  }

  if (!obj.periodo || typeof obj.periodo !== 'object') {
    return false;
  }

  const periodo = obj.periodo as Record<string, unknown>;
  if (typeof periodo.inicio !== 'string' || typeof periodo.fin !== 'string') {
    return false;
  }

  return true;
}

// ===========================================
// GENERIC UTILITIES
// ===========================================

/**
 * Safe JSON parse with type validation.
 * Parses JSON and validates against a type guard.
 *
 * @param json - JSON string to parse
 * @param validator - Type guard function to validate parsed data
 * @param fallback - Fallback value if parsing or validation fails
 */
export function safeJsonParseValidated<T>(
  json: string,
  validator: (value: unknown) => value is T,
  fallback: T | null = null
): T | null {
  try {
    const parsed = JSON.parse(json);
    return validator(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Asserts a value with runtime validation.
 * Throws if validation fails (use for critical paths where you want early failure).
 *
 * @param value - Value to validate
 * @param validator - Type guard function
 * @param errorMessage - Error message if validation fails
 */
export function assertValid<T>(
  value: unknown,
  validator: (value: unknown) => value is T,
  errorMessage: string
): asserts value is T {
  if (!validator(value)) {
    throw new Error(errorMessage);
  }
}

// ===========================================
// LOCALSTORAGE DATA TYPE GUARDS
// ===========================================

/**
 * Valid sensor types for satellite imagery.
 */
const VALID_SENSORS = ['Sentinel-1', 'Sentinel-2'] as const;

/**
 * Validates if a value is a valid SelectedImage from localStorage.
 * Used to prevent XSS and data corruption from localStorage.
 */
export interface SelectedImageShape {
  tile_url: string;
  target_date: string;
  sensor: 'Sentinel-1' | 'Sentinel-2';
  visualization: string;
  visualization_description: string;
  collection: string;
  images_count: number;
  selected_at: string;
  flood_info?: {
    id: string;
    name: string;
    description: string;
    severity: string;
  };
}

export function isValidSelectedImage(value: unknown): value is SelectedImageShape {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  // Required string fields
  if (typeof obj.tile_url !== 'string' || obj.tile_url.length === 0) return false;
  if (typeof obj.target_date !== 'string') return false;
  if (typeof obj.visualization !== 'string') return false;
  if (typeof obj.visualization_description !== 'string') return false;
  if (typeof obj.collection !== 'string') return false;
  if (typeof obj.selected_at !== 'string') return false;

  // Validate sensor is one of the allowed values
  if (!VALID_SENSORS.includes(obj.sensor as (typeof VALID_SENSORS)[number])) {
    return false;
  }

  // Required number field
  if (typeof obj.images_count !== 'number' || obj.images_count < 0) return false;

  // Validate tile_url is a valid URL pattern (basic security check)
  try {
    // Allow template placeholders by temporarily replacing them
    const testUrl = (obj.tile_url as string).replace(/\{[xyz]\}/g, '0');
    const parsed = new URL(testUrl);
    // Only allow HTTPS or valid Earth Engine URLs (by hostname)
    const hostname = parsed.hostname;
    const isEarthEngineHost = (ALLOWED_EARTH_ENGINE_HOSTNAMES as readonly string[]).includes(
      hostname,
    );
    if (parsed.protocol !== 'https:' || (!isEarthEngineHost && hostname.endsWith('.googleapis.com'))) {
      // Require HTTPS always, and only allow Earth Engine traffic to known hostnames
      return false;
    }
  } catch {
    return false;
  }

  // Optional flood_info validation
  if (obj.flood_info !== undefined) {
    if (obj.flood_info === null || typeof obj.flood_info !== 'object') {
      return false;
    }
    const flood = obj.flood_info as Record<string, unknown>;
    if (
      typeof flood.id !== 'string' ||
      typeof flood.name !== 'string' ||
      typeof flood.description !== 'string' ||
      typeof flood.severity !== 'string'
    ) {
      return false;
    }
  }

  return true;
}

/**
 * Validates if a value is a valid ImageComparison state from localStorage.
 */
export interface ImageComparisonShape {
  left: SelectedImageShape;
  right: SelectedImageShape;
  enabled: boolean;
}

export function isValidImageComparison(value: unknown): value is ImageComparisonShape {
  if (value === null || typeof value !== 'object') {
    return false;
  }

  const obj = value as Record<string, unknown>;

  // Validate enabled is boolean
  if (typeof obj.enabled !== 'boolean') return false;

  // Validate left and right are valid SelectedImage
  if (!isValidSelectedImage(obj.left)) return false;
  if (!isValidSelectedImage(obj.right)) return false;

  return true;
}
