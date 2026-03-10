/**
 * Runtime type guards and validators for the Consorcio Canalero application.
 * These functions validate data at runtime, especially for API responses
 * and JSON parsing where TypeScript assertions alone are insufficient.
 *
 * Pattern: Each type guard follows the signature `function isFoo(x: unknown): x is Foo`
 * This allows TypeScript to narrow the type in conditional blocks.
 */
// @ts-nocheck
function stryNS_9fa48() {
  var g = typeof globalThis === 'object' && globalThis && globalThis.Math === Math && globalThis || new Function("return this")();
  var ns = g.__stryker__ || (g.__stryker__ = {});
  if (ns.activeMutant === undefined && g.process && g.process.env && g.process.env.__STRYKER_ACTIVE_MUTANT__) {
    ns.activeMutant = g.process.env.__STRYKER_ACTIVE_MUTANT__;
  }
  function retrieveNS() {
    return ns;
  }
  stryNS_9fa48 = retrieveNS;
  return retrieveNS();
}
stryNS_9fa48();
function stryCov_9fa48() {
  var ns = stryNS_9fa48();
  var cov = ns.mutantCoverage || (ns.mutantCoverage = {
    static: {},
    perTest: {}
  });
  function cover() {
    var c = cov.static;
    if (ns.currentTestId) {
      c = cov.perTest[ns.currentTestId] = cov.perTest[ns.currentTestId] || {};
    }
    var a = arguments;
    for (var i = 0; i < a.length; i++) {
      c[a[i]] = (c[a[i]] || 0) + 1;
    }
  }
  stryCov_9fa48 = cover;
  cover.apply(null, arguments);
}
function stryMutAct_9fa48(id) {
  var ns = stryNS_9fa48();
  function isActive(id) {
    if (ns.activeMutant === id) {
      if (ns.hitCount !== void 0 && ++ns.hitCount > ns.hitLimit) {
        throw new Error('Stryker: Hit count limit reached (' + ns.hitCount + ')');
      }
      return true;
    }
    return false;
  }
  stryMutAct_9fa48 = isActive;
  return isActive(id);
}
import type { FeatureCollection, Geometry } from 'geojson';
import type { LayerStyle, Usuario } from '../types';

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
  if (stryMutAct_9fa48("361")) {
    {}
  } else {
    stryCov_9fa48("361");
    return stryMutAct_9fa48("364") ? typeof value === 'string' || VALID_USER_ROLES.includes(value as UserRole) : stryMutAct_9fa48("363") ? false : stryMutAct_9fa48("362") ? true : (stryCov_9fa48("362", "363", "364"), (stryMutAct_9fa48("366") ? typeof value !== 'string' : stryMutAct_9fa48("365") ? true : (stryCov_9fa48("365", "366"), typeof value === (stryMutAct_9fa48("367") ? "" : (stryCov_9fa48("367"), 'string')))) && VALID_USER_ROLES.includes(value as UserRole));
  }
}

/**
 * Safely extracts user role with runtime validation.
 * Returns the role if valid, null otherwise.
 */
export function safeGetUserRole(value: unknown): UserRole | null {
  if (stryMutAct_9fa48("368")) {
    {}
  } else {
    stryCov_9fa48("368");
    return isValidUserRole(value) ? value : null;
  }
}

/**
 * Validates if an object is a valid Usuario (user profile).
 * Checks for required fields and their types.
 */
export function isValidUsuario(value: unknown): value is Usuario {
  if (stryMutAct_9fa48("369")) {
    {}
  } else {
    stryCov_9fa48("369");
    if (stryMutAct_9fa48("372") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("371") ? false : stryMutAct_9fa48("370") ? true : (stryCov_9fa48("370", "371", "372"), (stryMutAct_9fa48("374") ? value !== null : stryMutAct_9fa48("373") ? false : (stryCov_9fa48("373", "374"), value === null)) || (stryMutAct_9fa48("376") ? typeof value === 'object' : stryMutAct_9fa48("375") ? false : (stryCov_9fa48("375", "376"), typeof value !== (stryMutAct_9fa48("377") ? "" : (stryCov_9fa48("377"), 'object')))))) {
      if (stryMutAct_9fa48("378")) {
        {}
      } else {
        stryCov_9fa48("378");
        return stryMutAct_9fa48("379") ? true : (stryCov_9fa48("379"), false);
      }
    }
    const obj = value as Record<string, unknown>;

    // Required fields
    if (stryMutAct_9fa48("382") ? typeof obj.id !== 'string' && obj.id.length === 0 : stryMutAct_9fa48("381") ? false : stryMutAct_9fa48("380") ? true : (stryCov_9fa48("380", "381", "382"), (stryMutAct_9fa48("384") ? typeof obj.id === 'string' : stryMutAct_9fa48("383") ? false : (stryCov_9fa48("383", "384"), typeof obj.id !== (stryMutAct_9fa48("385") ? "" : (stryCov_9fa48("385"), 'string')))) || (stryMutAct_9fa48("387") ? obj.id.length !== 0 : stryMutAct_9fa48("386") ? false : (stryCov_9fa48("386", "387"), obj.id.length === 0)))) {
      if (stryMutAct_9fa48("388")) {
        {}
      } else {
        stryCov_9fa48("388");
        return stryMutAct_9fa48("389") ? true : (stryCov_9fa48("389"), false);
      }
    }
    if (stryMutAct_9fa48("392") ? typeof obj.email === 'string' : stryMutAct_9fa48("391") ? false : stryMutAct_9fa48("390") ? true : (stryCov_9fa48("390", "391", "392"), typeof obj.email !== (stryMutAct_9fa48("393") ? "" : (stryCov_9fa48("393"), 'string')))) {
      if (stryMutAct_9fa48("394")) {
        {}
      } else {
        stryCov_9fa48("394");
        return stryMutAct_9fa48("395") ? true : (stryCov_9fa48("395"), false);
      }
    }
    if (stryMutAct_9fa48("398") ? false : stryMutAct_9fa48("397") ? true : stryMutAct_9fa48("396") ? isValidUserRole(obj.rol) : (stryCov_9fa48("396", "397", "398"), !isValidUserRole(obj.rol))) {
      if (stryMutAct_9fa48("399")) {
        {}
      } else {
        stryCov_9fa48("399");
        return stryMutAct_9fa48("400") ? true : (stryCov_9fa48("400"), false);
      }
    }

    // Optional fields - validate if present (allow null or string)
    if (stryMutAct_9fa48("403") ? obj.nombre !== undefined && obj.nombre !== null || typeof obj.nombre !== 'string' : stryMutAct_9fa48("402") ? false : stryMutAct_9fa48("401") ? true : (stryCov_9fa48("401", "402", "403"), (stryMutAct_9fa48("405") ? obj.nombre !== undefined || obj.nombre !== null : stryMutAct_9fa48("404") ? true : (stryCov_9fa48("404", "405"), (stryMutAct_9fa48("407") ? obj.nombre === undefined : stryMutAct_9fa48("406") ? true : (stryCov_9fa48("406", "407"), obj.nombre !== undefined)) && (stryMutAct_9fa48("409") ? obj.nombre === null : stryMutAct_9fa48("408") ? true : (stryCov_9fa48("408", "409"), obj.nombre !== null)))) && (stryMutAct_9fa48("411") ? typeof obj.nombre === 'string' : stryMutAct_9fa48("410") ? true : (stryCov_9fa48("410", "411"), typeof obj.nombre !== (stryMutAct_9fa48("412") ? "" : (stryCov_9fa48("412"), 'string')))))) {
      if (stryMutAct_9fa48("413")) {
        {}
      } else {
        stryCov_9fa48("413");
        return stryMutAct_9fa48("414") ? true : (stryCov_9fa48("414"), false);
      }
    }
    if (stryMutAct_9fa48("417") ? obj.telefono !== undefined && obj.telefono !== null || typeof obj.telefono !== 'string' : stryMutAct_9fa48("416") ? false : stryMutAct_9fa48("415") ? true : (stryCov_9fa48("415", "416", "417"), (stryMutAct_9fa48("419") ? obj.telefono !== undefined || obj.telefono !== null : stryMutAct_9fa48("418") ? true : (stryCov_9fa48("418", "419"), (stryMutAct_9fa48("421") ? obj.telefono === undefined : stryMutAct_9fa48("420") ? true : (stryCov_9fa48("420", "421"), obj.telefono !== undefined)) && (stryMutAct_9fa48("423") ? obj.telefono === null : stryMutAct_9fa48("422") ? true : (stryCov_9fa48("422", "423"), obj.telefono !== null)))) && (stryMutAct_9fa48("425") ? typeof obj.telefono === 'string' : stryMutAct_9fa48("424") ? true : (stryCov_9fa48("424", "425"), typeof obj.telefono !== (stryMutAct_9fa48("426") ? "" : (stryCov_9fa48("426"), 'string')))))) {
      if (stryMutAct_9fa48("427")) {
        {}
      } else {
        stryCov_9fa48("427");
        return stryMutAct_9fa48("428") ? true : (stryCov_9fa48("428"), false);
      }
    }
    return stryMutAct_9fa48("429") ? false : (stryCov_9fa48("429"), true);
  }
}

/**
 * Safely parses an API response as Usuario.
 * Returns null if validation fails.
 */
export function parseUsuario(data: unknown): Usuario | null {
  if (stryMutAct_9fa48("430")) {
    {}
  } else {
    stryCov_9fa48("430");
    return isValidUsuario(data) ? data : null;
  }
}

// ===========================================
// LAYER STYLE TYPE GUARDS
// ===========================================

/**
 * Validates if an object is a valid LayerStyle.
 */
export function isValidLayerStyle(value: unknown): value is LayerStyle {
  if (stryMutAct_9fa48("431")) {
    {}
  } else {
    stryCov_9fa48("431");
    if (stryMutAct_9fa48("434") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("433") ? false : stryMutAct_9fa48("432") ? true : (stryCov_9fa48("432", "433", "434"), (stryMutAct_9fa48("436") ? value !== null : stryMutAct_9fa48("435") ? false : (stryCov_9fa48("435", "436"), value === null)) || (stryMutAct_9fa48("438") ? typeof value === 'object' : stryMutAct_9fa48("437") ? false : (stryCov_9fa48("437", "438"), typeof value !== (stryMutAct_9fa48("439") ? "" : (stryCov_9fa48("439"), 'object')))))) {
      if (stryMutAct_9fa48("440")) {
        {}
      } else {
        stryCov_9fa48("440");
        return stryMutAct_9fa48("441") ? true : (stryCov_9fa48("441"), false);
      }
    }
    const obj = value as Record<string, unknown>;
    return stryMutAct_9fa48("444") ? typeof obj.color === 'string' && typeof obj.weight === 'number' && typeof obj.fillColor === 'string' && typeof obj.fillOpacity === 'number' && obj.fillOpacity >= 0 || obj.fillOpacity <= 1 : stryMutAct_9fa48("443") ? false : stryMutAct_9fa48("442") ? true : (stryCov_9fa48("442", "443", "444"), (stryMutAct_9fa48("446") ? typeof obj.color === 'string' && typeof obj.weight === 'number' && typeof obj.fillColor === 'string' && typeof obj.fillOpacity === 'number' || obj.fillOpacity >= 0 : stryMutAct_9fa48("445") ? true : (stryCov_9fa48("445", "446"), (stryMutAct_9fa48("448") ? typeof obj.color === 'string' && typeof obj.weight === 'number' && typeof obj.fillColor === 'string' || typeof obj.fillOpacity === 'number' : stryMutAct_9fa48("447") ? true : (stryCov_9fa48("447", "448"), (stryMutAct_9fa48("450") ? typeof obj.color === 'string' && typeof obj.weight === 'number' || typeof obj.fillColor === 'string' : stryMutAct_9fa48("449") ? true : (stryCov_9fa48("449", "450"), (stryMutAct_9fa48("452") ? typeof obj.color === 'string' || typeof obj.weight === 'number' : stryMutAct_9fa48("451") ? true : (stryCov_9fa48("451", "452"), (stryMutAct_9fa48("454") ? typeof obj.color !== 'string' : stryMutAct_9fa48("453") ? true : (stryCov_9fa48("453", "454"), typeof obj.color === (stryMutAct_9fa48("455") ? "" : (stryCov_9fa48("455"), 'string')))) && (stryMutAct_9fa48("457") ? typeof obj.weight !== 'number' : stryMutAct_9fa48("456") ? true : (stryCov_9fa48("456", "457"), typeof obj.weight === (stryMutAct_9fa48("458") ? "" : (stryCov_9fa48("458"), 'number')))))) && (stryMutAct_9fa48("460") ? typeof obj.fillColor !== 'string' : stryMutAct_9fa48("459") ? true : (stryCov_9fa48("459", "460"), typeof obj.fillColor === (stryMutAct_9fa48("461") ? "" : (stryCov_9fa48("461"), 'string')))))) && (stryMutAct_9fa48("463") ? typeof obj.fillOpacity !== 'number' : stryMutAct_9fa48("462") ? true : (stryCov_9fa48("462", "463"), typeof obj.fillOpacity === (stryMutAct_9fa48("464") ? "" : (stryCov_9fa48("464"), 'number')))))) && (stryMutAct_9fa48("467") ? obj.fillOpacity < 0 : stryMutAct_9fa48("466") ? obj.fillOpacity > 0 : stryMutAct_9fa48("465") ? true : (stryCov_9fa48("465", "466", "467"), obj.fillOpacity >= 0)))) && (stryMutAct_9fa48("470") ? obj.fillOpacity > 1 : stryMutAct_9fa48("469") ? obj.fillOpacity < 1 : stryMutAct_9fa48("468") ? true : (stryCov_9fa48("468", "469", "470"), obj.fillOpacity <= 1)));
  }
}

/**
 * Safely parses layer style from JSON string or object.
 * Returns a default style if parsing fails.
 */
export function parseLayerStyle(value: string | LayerStyle | unknown, defaultColor = stryMutAct_9fa48("471") ? "" : (stryCov_9fa48("471"), '#3388ff')): LayerStyle {
  if (stryMutAct_9fa48("472")) {
    {}
  } else {
    stryCov_9fa48("472");
    const defaultStyle: LayerStyle = stryMutAct_9fa48("473") ? {} : (stryCov_9fa48("473"), {
      color: defaultColor,
      weight: 2,
      fillColor: defaultColor,
      fillOpacity: 0.1
    });
    if (stryMutAct_9fa48("476") ? typeof value !== 'string' : stryMutAct_9fa48("475") ? false : stryMutAct_9fa48("474") ? true : (stryCov_9fa48("474", "475", "476"), typeof value === (stryMutAct_9fa48("477") ? "" : (stryCov_9fa48("477"), 'string')))) {
      if (stryMutAct_9fa48("478")) {
        {}
      } else {
        stryCov_9fa48("478");
        try {
          if (stryMutAct_9fa48("479")) {
            {}
          } else {
            stryCov_9fa48("479");
            const parsed = JSON.parse(value);
            return isValidLayerStyle(parsed) ? parsed : defaultStyle;
          }
        } catch {
          if (stryMutAct_9fa48("480")) {
            {}
          } else {
            stryCov_9fa48("480");
            return defaultStyle;
          }
        }
      }
    }
    return isValidLayerStyle(value) ? value : defaultStyle;
  }
}

/**
 * Extracts color from layer style with fallback.
 */
export function getStyleColor(estilo: string | LayerStyle | unknown, defaultColor = stryMutAct_9fa48("481") ? "" : (stryCov_9fa48("481"), '#3388ff')): string {
  if (stryMutAct_9fa48("482")) {
    {}
  } else {
    stryCov_9fa48("482");
    const style = parseLayerStyle(estilo, defaultColor);
    return style.color;
  }
}

// ===========================================
// GEOJSON TYPE GUARDS
// ===========================================

/** Valid GeoJSON geometry types */
const VALID_GEOMETRY_TYPES = ['Point', 'MultiPoint', 'LineString', 'MultiLineString', 'Polygon', 'MultiPolygon', 'GeometryCollection'] as const;

/**
 * Validates if a value is a valid GeoJSON Geometry.
 */
export function isValidGeometry(value: unknown): value is Geometry {
  if (stryMutAct_9fa48("483")) {
    {}
  } else {
    stryCov_9fa48("483");
    if (stryMutAct_9fa48("486") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("485") ? false : stryMutAct_9fa48("484") ? true : (stryCov_9fa48("484", "485", "486"), (stryMutAct_9fa48("488") ? value !== null : stryMutAct_9fa48("487") ? false : (stryCov_9fa48("487", "488"), value === null)) || (stryMutAct_9fa48("490") ? typeof value === 'object' : stryMutAct_9fa48("489") ? false : (stryCov_9fa48("489", "490"), typeof value !== (stryMutAct_9fa48("491") ? "" : (stryCov_9fa48("491"), 'object')))))) {
      if (stryMutAct_9fa48("492")) {
        {}
      } else {
        stryCov_9fa48("492");
        return stryMutAct_9fa48("493") ? true : (stryCov_9fa48("493"), false);
      }
    }
    const obj = value as Record<string, unknown>;
    if (stryMutAct_9fa48("496") ? typeof obj.type === 'string' : stryMutAct_9fa48("495") ? false : stryMutAct_9fa48("494") ? true : (stryCov_9fa48("494", "495", "496"), typeof obj.type !== (stryMutAct_9fa48("497") ? "" : (stryCov_9fa48("497"), 'string')))) {
      if (stryMutAct_9fa48("498")) {
        {}
      } else {
        stryCov_9fa48("498");
        return stryMutAct_9fa48("499") ? true : (stryCov_9fa48("499"), false);
      }
    }
    if (stryMutAct_9fa48("502") ? false : stryMutAct_9fa48("501") ? true : stryMutAct_9fa48("500") ? VALID_GEOMETRY_TYPES.includes(obj.type as (typeof VALID_GEOMETRY_TYPES)[number]) : (stryCov_9fa48("500", "501", "502"), !VALID_GEOMETRY_TYPES.includes(obj.type as (typeof VALID_GEOMETRY_TYPES)[number]))) {
      if (stryMutAct_9fa48("503")) {
        {}
      } else {
        stryCov_9fa48("503");
        return stryMutAct_9fa48("504") ? true : (stryCov_9fa48("504"), false);
      }
    }

    // GeometryCollection has 'geometries' instead of 'coordinates'
    if (stryMutAct_9fa48("507") ? obj.type !== 'GeometryCollection' : stryMutAct_9fa48("506") ? false : stryMutAct_9fa48("505") ? true : (stryCov_9fa48("505", "506", "507"), obj.type === (stryMutAct_9fa48("508") ? "" : (stryCov_9fa48("508"), 'GeometryCollection')))) {
      if (stryMutAct_9fa48("509")) {
        {}
      } else {
        stryCov_9fa48("509");
        return Array.isArray(obj.geometries);
      }
    }
    return Array.isArray(obj.coordinates);
  }
}

/**
 * Validates if a value is a valid GeoJSON FeatureCollection.
 */
export function isValidFeatureCollection(value: unknown): value is FeatureCollection {
  if (stryMutAct_9fa48("510")) {
    {}
  } else {
    stryCov_9fa48("510");
    if (stryMutAct_9fa48("513") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("512") ? false : stryMutAct_9fa48("511") ? true : (stryCov_9fa48("511", "512", "513"), (stryMutAct_9fa48("515") ? value !== null : stryMutAct_9fa48("514") ? false : (stryCov_9fa48("514", "515"), value === null)) || (stryMutAct_9fa48("517") ? typeof value === 'object' : stryMutAct_9fa48("516") ? false : (stryCov_9fa48("516", "517"), typeof value !== (stryMutAct_9fa48("518") ? "" : (stryCov_9fa48("518"), 'object')))))) {
      if (stryMutAct_9fa48("519")) {
        {}
      } else {
        stryCov_9fa48("519");
        return stryMutAct_9fa48("520") ? true : (stryCov_9fa48("520"), false);
      }
    }
    const obj = value as Record<string, unknown>;
    if (stryMutAct_9fa48("523") ? obj.type === 'FeatureCollection' : stryMutAct_9fa48("522") ? false : stryMutAct_9fa48("521") ? true : (stryCov_9fa48("521", "522", "523"), obj.type !== (stryMutAct_9fa48("524") ? "" : (stryCov_9fa48("524"), 'FeatureCollection')))) {
      if (stryMutAct_9fa48("525")) {
        {}
      } else {
        stryCov_9fa48("525");
        return stryMutAct_9fa48("526") ? true : (stryCov_9fa48("526"), false);
      }
    }
    if (stryMutAct_9fa48("529") ? false : stryMutAct_9fa48("528") ? true : stryMutAct_9fa48("527") ? Array.isArray(obj.features) : (stryCov_9fa48("527", "528", "529"), !Array.isArray(obj.features))) {
      if (stryMutAct_9fa48("530")) {
        {}
      } else {
        stryCov_9fa48("530");
        return stryMutAct_9fa48("531") ? true : (stryCov_9fa48("531"), false);
      }
    }

    // Validate each feature has at minimum type and geometry
    return stryMutAct_9fa48("532") ? obj.features.some(feature => {
      if (feature === null || typeof feature !== 'object') {
        return false;
      }
      const f = feature as Record<string, unknown>;
      return f.type === 'Feature' && (f.geometry === null || isValidGeometry(f.geometry));
    }) : (stryCov_9fa48("532"), obj.features.every(feature => {
      if (stryMutAct_9fa48("533")) {
        {}
      } else {
        stryCov_9fa48("533");
        if (stryMutAct_9fa48("536") ? feature === null && typeof feature !== 'object' : stryMutAct_9fa48("535") ? false : stryMutAct_9fa48("534") ? true : (stryCov_9fa48("534", "535", "536"), (stryMutAct_9fa48("538") ? feature !== null : stryMutAct_9fa48("537") ? false : (stryCov_9fa48("537", "538"), feature === null)) || (stryMutAct_9fa48("540") ? typeof feature === 'object' : stryMutAct_9fa48("539") ? false : (stryCov_9fa48("539", "540"), typeof feature !== (stryMutAct_9fa48("541") ? "" : (stryCov_9fa48("541"), 'object')))))) {
          if (stryMutAct_9fa48("542")) {
            {}
          } else {
            stryCov_9fa48("542");
            return stryMutAct_9fa48("543") ? true : (stryCov_9fa48("543"), false);
          }
        }
        const f = feature as Record<string, unknown>;
        return stryMutAct_9fa48("546") ? f.type === 'Feature' || f.geometry === null || isValidGeometry(f.geometry) : stryMutAct_9fa48("545") ? false : stryMutAct_9fa48("544") ? true : (stryCov_9fa48("544", "545", "546"), (stryMutAct_9fa48("548") ? f.type !== 'Feature' : stryMutAct_9fa48("547") ? true : (stryCov_9fa48("547", "548"), f.type === (stryMutAct_9fa48("549") ? "" : (stryCov_9fa48("549"), 'Feature')))) && (stryMutAct_9fa48("551") ? f.geometry === null && isValidGeometry(f.geometry) : stryMutAct_9fa48("550") ? true : (stryCov_9fa48("550", "551"), (stryMutAct_9fa48("553") ? f.geometry !== null : stryMutAct_9fa48("552") ? false : (stryCov_9fa48("552", "553"), f.geometry === null)) || isValidGeometry(f.geometry))));
      }
    }));
  }
}

/**
 * Safely parses an API response as FeatureCollection.
 * Returns null if validation fails.
 */
export function parseFeatureCollection(data: unknown): FeatureCollection | null {
  if (stryMutAct_9fa48("554")) {
    {}
  } else {
    stryCov_9fa48("554");
    return isValidFeatureCollection(data) ? data : null;
  }
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
  periodo: {
    inicio: string;
    fin: string;
  };
} {
  if (stryMutAct_9fa48("555")) {
    {}
  } else {
    stryCov_9fa48("555");
    if (stryMutAct_9fa48("558") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("557") ? false : stryMutAct_9fa48("556") ? true : (stryCov_9fa48("556", "557", "558"), (stryMutAct_9fa48("560") ? value !== null : stryMutAct_9fa48("559") ? false : (stryCov_9fa48("559", "560"), value === null)) || (stryMutAct_9fa48("562") ? typeof value === 'object' : stryMutAct_9fa48("561") ? false : (stryCov_9fa48("561", "562"), typeof value !== (stryMutAct_9fa48("563") ? "" : (stryCov_9fa48("563"), 'object')))))) {
      if (stryMutAct_9fa48("564")) {
        {}
      } else {
        stryCov_9fa48("564");
        return stryMutAct_9fa48("565") ? true : (stryCov_9fa48("565"), false);
      }
    }
    const obj = value as Record<string, unknown>;

    // Validate summary
    if (stryMutAct_9fa48("568") ? !obj.summary && typeof obj.summary !== 'object' : stryMutAct_9fa48("567") ? false : stryMutAct_9fa48("566") ? true : (stryCov_9fa48("566", "567", "568"), (stryMutAct_9fa48("569") ? obj.summary : (stryCov_9fa48("569"), !obj.summary)) || (stryMutAct_9fa48("571") ? typeof obj.summary === 'object' : stryMutAct_9fa48("570") ? false : (stryCov_9fa48("570", "571"), typeof obj.summary !== (stryMutAct_9fa48("572") ? "" : (stryCov_9fa48("572"), 'object')))))) {
      if (stryMutAct_9fa48("573")) {
        {}
      } else {
        stryCov_9fa48("573");
        return stryMutAct_9fa48("574") ? true : (stryCov_9fa48("574"), false);
      }
    }
    const summary = obj.summary as Record<string, unknown>;
    if (stryMutAct_9fa48("577") ? (typeof summary.area_total_ha !== 'number' || typeof summary.area_productiva_ha !== 'number' || typeof summary.area_problematica_ha !== 'number') && typeof summary.porcentaje_problematico !== 'number' : stryMutAct_9fa48("576") ? false : stryMutAct_9fa48("575") ? true : (stryCov_9fa48("575", "576", "577"), (stryMutAct_9fa48("579") ? (typeof summary.area_total_ha !== 'number' || typeof summary.area_productiva_ha !== 'number') && typeof summary.area_problematica_ha !== 'number' : stryMutAct_9fa48("578") ? false : (stryCov_9fa48("578", "579"), (stryMutAct_9fa48("581") ? typeof summary.area_total_ha !== 'number' && typeof summary.area_productiva_ha !== 'number' : stryMutAct_9fa48("580") ? false : (stryCov_9fa48("580", "581"), (stryMutAct_9fa48("583") ? typeof summary.area_total_ha === 'number' : stryMutAct_9fa48("582") ? false : (stryCov_9fa48("582", "583"), typeof summary.area_total_ha !== (stryMutAct_9fa48("584") ? "" : (stryCov_9fa48("584"), 'number')))) || (stryMutAct_9fa48("586") ? typeof summary.area_productiva_ha === 'number' : stryMutAct_9fa48("585") ? false : (stryCov_9fa48("585", "586"), typeof summary.area_productiva_ha !== (stryMutAct_9fa48("587") ? "" : (stryCov_9fa48("587"), 'number')))))) || (stryMutAct_9fa48("589") ? typeof summary.area_problematica_ha === 'number' : stryMutAct_9fa48("588") ? false : (stryCov_9fa48("588", "589"), typeof summary.area_problematica_ha !== (stryMutAct_9fa48("590") ? "" : (stryCov_9fa48("590"), 'number')))))) || (stryMutAct_9fa48("592") ? typeof summary.porcentaje_problematico === 'number' : stryMutAct_9fa48("591") ? false : (stryCov_9fa48("591", "592"), typeof summary.porcentaje_problematico !== (stryMutAct_9fa48("593") ? "" : (stryCov_9fa48("593"), 'number')))))) {
      if (stryMutAct_9fa48("594")) {
        {}
      } else {
        stryCov_9fa48("594");
        return stryMutAct_9fa48("595") ? true : (stryCov_9fa48("595"), false);
      }
    }

    // Validate other required fields exist
    if (stryMutAct_9fa48("598") ? typeof obj.clasificacion !== 'object' && obj.clasificacion === null : stryMutAct_9fa48("597") ? false : stryMutAct_9fa48("596") ? true : (stryCov_9fa48("596", "597", "598"), (stryMutAct_9fa48("600") ? typeof obj.clasificacion === 'object' : stryMutAct_9fa48("599") ? false : (stryCov_9fa48("599", "600"), typeof obj.clasificacion !== (stryMutAct_9fa48("601") ? "" : (stryCov_9fa48("601"), 'object')))) || (stryMutAct_9fa48("603") ? obj.clasificacion !== null : stryMutAct_9fa48("602") ? false : (stryCov_9fa48("602", "603"), obj.clasificacion === null)))) {
      if (stryMutAct_9fa48("604")) {
        {}
      } else {
        stryCov_9fa48("604");
        return stryMutAct_9fa48("605") ? true : (stryCov_9fa48("605"), false);
      }
    }
    if (stryMutAct_9fa48("608") ? false : stryMutAct_9fa48("607") ? true : stryMutAct_9fa48("606") ? Array.isArray(obj.ranking_cuencas) : (stryCov_9fa48("606", "607", "608"), !Array.isArray(obj.ranking_cuencas))) {
      if (stryMutAct_9fa48("609")) {
        {}
      } else {
        stryCov_9fa48("609");
        return stryMutAct_9fa48("610") ? true : (stryCov_9fa48("610"), false);
      }
    }
    if (stryMutAct_9fa48("613") ? false : stryMutAct_9fa48("612") ? true : stryMutAct_9fa48("611") ? Array.isArray(obj.alertas) : (stryCov_9fa48("611", "612", "613"), !Array.isArray(obj.alertas))) {
      if (stryMutAct_9fa48("614")) {
        {}
      } else {
        stryCov_9fa48("614");
        return stryMutAct_9fa48("615") ? true : (stryCov_9fa48("615"), false);
      }
    }
    if (stryMutAct_9fa48("618") ? !obj.periodo && typeof obj.periodo !== 'object' : stryMutAct_9fa48("617") ? false : stryMutAct_9fa48("616") ? true : (stryCov_9fa48("616", "617", "618"), (stryMutAct_9fa48("619") ? obj.periodo : (stryCov_9fa48("619"), !obj.periodo)) || (stryMutAct_9fa48("621") ? typeof obj.periodo === 'object' : stryMutAct_9fa48("620") ? false : (stryCov_9fa48("620", "621"), typeof obj.periodo !== (stryMutAct_9fa48("622") ? "" : (stryCov_9fa48("622"), 'object')))))) {
      if (stryMutAct_9fa48("623")) {
        {}
      } else {
        stryCov_9fa48("623");
        return stryMutAct_9fa48("624") ? true : (stryCov_9fa48("624"), false);
      }
    }
    const periodo = obj.periodo as Record<string, unknown>;
    if (stryMutAct_9fa48("627") ? typeof periodo.inicio !== 'string' && typeof periodo.fin !== 'string' : stryMutAct_9fa48("626") ? false : stryMutAct_9fa48("625") ? true : (stryCov_9fa48("625", "626", "627"), (stryMutAct_9fa48("629") ? typeof periodo.inicio === 'string' : stryMutAct_9fa48("628") ? false : (stryCov_9fa48("628", "629"), typeof periodo.inicio !== (stryMutAct_9fa48("630") ? "" : (stryCov_9fa48("630"), 'string')))) || (stryMutAct_9fa48("632") ? typeof periodo.fin === 'string' : stryMutAct_9fa48("631") ? false : (stryCov_9fa48("631", "632"), typeof periodo.fin !== (stryMutAct_9fa48("633") ? "" : (stryCov_9fa48("633"), 'string')))))) {
      if (stryMutAct_9fa48("634")) {
        {}
      } else {
        stryCov_9fa48("634");
        return stryMutAct_9fa48("635") ? true : (stryCov_9fa48("635"), false);
      }
    }
    return stryMutAct_9fa48("636") ? false : (stryCov_9fa48("636"), true);
  }
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
export function safeJsonParseValidated<T>(json: string, validator: (value: unknown) => value is T, fallback: T | null = null): T | null {
  if (stryMutAct_9fa48("637")) {
    {}
  } else {
    stryCov_9fa48("637");
    try {
      if (stryMutAct_9fa48("638")) {
        {}
      } else {
        stryCov_9fa48("638");
        const parsed = JSON.parse(json);
        return validator(parsed) ? parsed : fallback;
      }
    } catch {
      if (stryMutAct_9fa48("639")) {
        {}
      } else {
        stryCov_9fa48("639");
        return fallback;
      }
    }
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
export function assertValid<T>(value: unknown, validator: (value: unknown) => value is T, errorMessage: string): asserts value is T {
  if (stryMutAct_9fa48("640")) {
    {}
  } else {
    stryCov_9fa48("640");
    if (stryMutAct_9fa48("643") ? false : stryMutAct_9fa48("642") ? true : stryMutAct_9fa48("641") ? validator(value) : (stryCov_9fa48("641", "642", "643"), !validator(value))) {
      if (stryMutAct_9fa48("644")) {
        {}
      } else {
        stryCov_9fa48("644");
        throw new Error(errorMessage);
      }
    }
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
  if (stryMutAct_9fa48("645")) {
    {}
  } else {
    stryCov_9fa48("645");
    if (stryMutAct_9fa48("648") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("647") ? false : stryMutAct_9fa48("646") ? true : (stryCov_9fa48("646", "647", "648"), (stryMutAct_9fa48("650") ? value !== null : stryMutAct_9fa48("649") ? false : (stryCov_9fa48("649", "650"), value === null)) || (stryMutAct_9fa48("652") ? typeof value === 'object' : stryMutAct_9fa48("651") ? false : (stryCov_9fa48("651", "652"), typeof value !== (stryMutAct_9fa48("653") ? "" : (stryCov_9fa48("653"), 'object')))))) {
      if (stryMutAct_9fa48("654")) {
        {}
      } else {
        stryCov_9fa48("654");
        return stryMutAct_9fa48("655") ? true : (stryCov_9fa48("655"), false);
      }
    }
    const obj = value as Record<string, unknown>;

    // Required string fields
    if (stryMutAct_9fa48("658") ? typeof obj.tile_url !== 'string' && obj.tile_url.length === 0 : stryMutAct_9fa48("657") ? false : stryMutAct_9fa48("656") ? true : (stryCov_9fa48("656", "657", "658"), (stryMutAct_9fa48("660") ? typeof obj.tile_url === 'string' : stryMutAct_9fa48("659") ? false : (stryCov_9fa48("659", "660"), typeof obj.tile_url !== (stryMutAct_9fa48("661") ? "" : (stryCov_9fa48("661"), 'string')))) || (stryMutAct_9fa48("663") ? obj.tile_url.length !== 0 : stryMutAct_9fa48("662") ? false : (stryCov_9fa48("662", "663"), obj.tile_url.length === 0)))) return stryMutAct_9fa48("664") ? true : (stryCov_9fa48("664"), false);
    if (stryMutAct_9fa48("667") ? typeof obj.target_date === 'string' : stryMutAct_9fa48("666") ? false : stryMutAct_9fa48("665") ? true : (stryCov_9fa48("665", "666", "667"), typeof obj.target_date !== (stryMutAct_9fa48("668") ? "" : (stryCov_9fa48("668"), 'string')))) return stryMutAct_9fa48("669") ? true : (stryCov_9fa48("669"), false);
    if (stryMutAct_9fa48("672") ? typeof obj.visualization === 'string' : stryMutAct_9fa48("671") ? false : stryMutAct_9fa48("670") ? true : (stryCov_9fa48("670", "671", "672"), typeof obj.visualization !== (stryMutAct_9fa48("673") ? "" : (stryCov_9fa48("673"), 'string')))) return stryMutAct_9fa48("674") ? true : (stryCov_9fa48("674"), false);
    if (stryMutAct_9fa48("677") ? typeof obj.visualization_description === 'string' : stryMutAct_9fa48("676") ? false : stryMutAct_9fa48("675") ? true : (stryCov_9fa48("675", "676", "677"), typeof obj.visualization_description !== (stryMutAct_9fa48("678") ? "" : (stryCov_9fa48("678"), 'string')))) return stryMutAct_9fa48("679") ? true : (stryCov_9fa48("679"), false);
    if (stryMutAct_9fa48("682") ? typeof obj.collection === 'string' : stryMutAct_9fa48("681") ? false : stryMutAct_9fa48("680") ? true : (stryCov_9fa48("680", "681", "682"), typeof obj.collection !== (stryMutAct_9fa48("683") ? "" : (stryCov_9fa48("683"), 'string')))) return stryMutAct_9fa48("684") ? true : (stryCov_9fa48("684"), false);
    if (stryMutAct_9fa48("687") ? typeof obj.selected_at === 'string' : stryMutAct_9fa48("686") ? false : stryMutAct_9fa48("685") ? true : (stryCov_9fa48("685", "686", "687"), typeof obj.selected_at !== (stryMutAct_9fa48("688") ? "" : (stryCov_9fa48("688"), 'string')))) return stryMutAct_9fa48("689") ? true : (stryCov_9fa48("689"), false);

    // Validate sensor is one of the allowed values
    if (stryMutAct_9fa48("692") ? false : stryMutAct_9fa48("691") ? true : stryMutAct_9fa48("690") ? VALID_SENSORS.includes(obj.sensor as (typeof VALID_SENSORS)[number]) : (stryCov_9fa48("690", "691", "692"), !VALID_SENSORS.includes(obj.sensor as (typeof VALID_SENSORS)[number]))) {
      if (stryMutAct_9fa48("693")) {
        {}
      } else {
        stryCov_9fa48("693");
        return stryMutAct_9fa48("694") ? true : (stryCov_9fa48("694"), false);
      }
    }

    // Required number field
    if (stryMutAct_9fa48("697") ? typeof obj.images_count !== 'number' && obj.images_count < 0 : stryMutAct_9fa48("696") ? false : stryMutAct_9fa48("695") ? true : (stryCov_9fa48("695", "696", "697"), (stryMutAct_9fa48("699") ? typeof obj.images_count === 'number' : stryMutAct_9fa48("698") ? false : (stryCov_9fa48("698", "699"), typeof obj.images_count !== (stryMutAct_9fa48("700") ? "" : (stryCov_9fa48("700"), 'number')))) || (stryMutAct_9fa48("703") ? obj.images_count >= 0 : stryMutAct_9fa48("702") ? obj.images_count <= 0 : stryMutAct_9fa48("701") ? false : (stryCov_9fa48("701", "702", "703"), obj.images_count < 0)))) return stryMutAct_9fa48("704") ? true : (stryCov_9fa48("704"), false);

    // Validate tile_url is a valid URL pattern (basic security check)
    try {
      if (stryMutAct_9fa48("705")) {
        {}
      } else {
        stryCov_9fa48("705");
        // Allow template placeholders by temporarily replacing them
        const testUrl = (obj.tile_url as string).replace(stryMutAct_9fa48("706") ? /\{[^xyz]\}/g : (stryCov_9fa48("706"), /\{[xyz]\}/g), stryMutAct_9fa48("707") ? "" : (stryCov_9fa48("707"), '0'));
        const parsed = new URL(testUrl);
        // Only allow HTTPS or valid Earth Engine URLs (by hostname)
        const hostname = parsed.hostname;
        const isEarthEngineHost = (ALLOWED_EARTH_ENGINE_HOSTNAMES as readonly string[]).includes(hostname);
        if (stryMutAct_9fa48("710") ? parsed.protocol !== 'https:' && !isEarthEngineHost && hostname.endsWith('.googleapis.com') : stryMutAct_9fa48("709") ? false : stryMutAct_9fa48("708") ? true : (stryCov_9fa48("708", "709", "710"), (stryMutAct_9fa48("712") ? parsed.protocol === 'https:' : stryMutAct_9fa48("711") ? false : (stryCov_9fa48("711", "712"), parsed.protocol !== (stryMutAct_9fa48("713") ? "" : (stryCov_9fa48("713"), 'https:')))) || (stryMutAct_9fa48("715") ? !isEarthEngineHost || hostname.endsWith('.googleapis.com') : stryMutAct_9fa48("714") ? false : (stryCov_9fa48("714", "715"), (stryMutAct_9fa48("716") ? isEarthEngineHost : (stryCov_9fa48("716"), !isEarthEngineHost)) && (stryMutAct_9fa48("717") ? hostname.startsWith('.googleapis.com') : (stryCov_9fa48("717"), hostname.endsWith(stryMutAct_9fa48("718") ? "" : (stryCov_9fa48("718"), '.googleapis.com')))))))) {
          if (stryMutAct_9fa48("719")) {
            {}
          } else {
            stryCov_9fa48("719");
            // Require HTTPS always, and only allow Earth Engine traffic to known hostnames
            return stryMutAct_9fa48("720") ? true : (stryCov_9fa48("720"), false);
          }
        }
      }
    } catch {
      if (stryMutAct_9fa48("721")) {
        {}
      } else {
        stryCov_9fa48("721");
        return stryMutAct_9fa48("722") ? true : (stryCov_9fa48("722"), false);
      }
    }

    // Optional flood_info validation
    if (stryMutAct_9fa48("725") ? obj.flood_info === undefined : stryMutAct_9fa48("724") ? false : stryMutAct_9fa48("723") ? true : (stryCov_9fa48("723", "724", "725"), obj.flood_info !== undefined)) {
      if (stryMutAct_9fa48("726")) {
        {}
      } else {
        stryCov_9fa48("726");
        if (stryMutAct_9fa48("729") ? obj.flood_info === null && typeof obj.flood_info !== 'object' : stryMutAct_9fa48("728") ? false : stryMutAct_9fa48("727") ? true : (stryCov_9fa48("727", "728", "729"), (stryMutAct_9fa48("731") ? obj.flood_info !== null : stryMutAct_9fa48("730") ? false : (stryCov_9fa48("730", "731"), obj.flood_info === null)) || (stryMutAct_9fa48("733") ? typeof obj.flood_info === 'object' : stryMutAct_9fa48("732") ? false : (stryCov_9fa48("732", "733"), typeof obj.flood_info !== (stryMutAct_9fa48("734") ? "" : (stryCov_9fa48("734"), 'object')))))) {
          if (stryMutAct_9fa48("735")) {
            {}
          } else {
            stryCov_9fa48("735");
            return stryMutAct_9fa48("736") ? true : (stryCov_9fa48("736"), false);
          }
        }
        const flood = obj.flood_info as Record<string, unknown>;
        if (stryMutAct_9fa48("739") ? (typeof flood.id !== 'string' || typeof flood.name !== 'string' || typeof flood.description !== 'string') && typeof flood.severity !== 'string' : stryMutAct_9fa48("738") ? false : stryMutAct_9fa48("737") ? true : (stryCov_9fa48("737", "738", "739"), (stryMutAct_9fa48("741") ? (typeof flood.id !== 'string' || typeof flood.name !== 'string') && typeof flood.description !== 'string' : stryMutAct_9fa48("740") ? false : (stryCov_9fa48("740", "741"), (stryMutAct_9fa48("743") ? typeof flood.id !== 'string' && typeof flood.name !== 'string' : stryMutAct_9fa48("742") ? false : (stryCov_9fa48("742", "743"), (stryMutAct_9fa48("745") ? typeof flood.id === 'string' : stryMutAct_9fa48("744") ? false : (stryCov_9fa48("744", "745"), typeof flood.id !== (stryMutAct_9fa48("746") ? "" : (stryCov_9fa48("746"), 'string')))) || (stryMutAct_9fa48("748") ? typeof flood.name === 'string' : stryMutAct_9fa48("747") ? false : (stryCov_9fa48("747", "748"), typeof flood.name !== (stryMutAct_9fa48("749") ? "" : (stryCov_9fa48("749"), 'string')))))) || (stryMutAct_9fa48("751") ? typeof flood.description === 'string' : stryMutAct_9fa48("750") ? false : (stryCov_9fa48("750", "751"), typeof flood.description !== (stryMutAct_9fa48("752") ? "" : (stryCov_9fa48("752"), 'string')))))) || (stryMutAct_9fa48("754") ? typeof flood.severity === 'string' : stryMutAct_9fa48("753") ? false : (stryCov_9fa48("753", "754"), typeof flood.severity !== (stryMutAct_9fa48("755") ? "" : (stryCov_9fa48("755"), 'string')))))) {
          if (stryMutAct_9fa48("756")) {
            {}
          } else {
            stryCov_9fa48("756");
            return stryMutAct_9fa48("757") ? true : (stryCov_9fa48("757"), false);
          }
        }
      }
    }
    return stryMutAct_9fa48("758") ? false : (stryCov_9fa48("758"), true);
  }
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
  if (stryMutAct_9fa48("759")) {
    {}
  } else {
    stryCov_9fa48("759");
    if (stryMutAct_9fa48("762") ? value === null && typeof value !== 'object' : stryMutAct_9fa48("761") ? false : stryMutAct_9fa48("760") ? true : (stryCov_9fa48("760", "761", "762"), (stryMutAct_9fa48("764") ? value !== null : stryMutAct_9fa48("763") ? false : (stryCov_9fa48("763", "764"), value === null)) || (stryMutAct_9fa48("766") ? typeof value === 'object' : stryMutAct_9fa48("765") ? false : (stryCov_9fa48("765", "766"), typeof value !== (stryMutAct_9fa48("767") ? "" : (stryCov_9fa48("767"), 'object')))))) {
      if (stryMutAct_9fa48("768")) {
        {}
      } else {
        stryCov_9fa48("768");
        return stryMutAct_9fa48("769") ? true : (stryCov_9fa48("769"), false);
      }
    }
    const obj = value as Record<string, unknown>;

    // Validate enabled is boolean
    if (stryMutAct_9fa48("772") ? typeof obj.enabled === 'boolean' : stryMutAct_9fa48("771") ? false : stryMutAct_9fa48("770") ? true : (stryCov_9fa48("770", "771", "772"), typeof obj.enabled !== (stryMutAct_9fa48("773") ? "" : (stryCov_9fa48("773"), 'boolean')))) return stryMutAct_9fa48("774") ? true : (stryCov_9fa48("774"), false);

    // Validate left and right are valid SelectedImage
    if (stryMutAct_9fa48("777") ? false : stryMutAct_9fa48("776") ? true : stryMutAct_9fa48("775") ? isValidSelectedImage(obj.left) : (stryCov_9fa48("775", "776", "777"), !isValidSelectedImage(obj.left))) return stryMutAct_9fa48("778") ? true : (stryCov_9fa48("778"), false);
    if (stryMutAct_9fa48("781") ? false : stryMutAct_9fa48("780") ? true : stryMutAct_9fa48("779") ? isValidSelectedImage(obj.right) : (stryCov_9fa48("779", "780", "781"), !isValidSelectedImage(obj.right))) return stryMutAct_9fa48("782") ? true : (stryCov_9fa48("782"), false);
    return stryMutAct_9fa48("783") ? false : (stryCov_9fa48("783"), true);
  }
}