/**
 * rainfallMultiParcelHarness.ts — pure helper for the rainfall multi-parcel
 * E2E harness (W2 + W6 of change `rainfall-multi-parcel-e2e-harness`).
 *
 * STRICTLY PURE: no Playwright, no `page`, no DOM side effects beyond the
 * `RectCss`/occlusion inputs the caller supplies. The Vitest layer (this file
 * + `tests/unit/rainfallMultiParcelHarness.test.ts`) pins the contracts; the
 * Playwright state-machine layer (W7/W8) imports these pure functions and feeds
 * them live `getBoundingClientRect()` rectangles, an occlusion snapshot, and
 * the intercepted request trace.
 *
 * Why projection is in CSS pixels from the live canvas rect (design JD-DES-001):
 *   `devicePixelRatio` and backing-store size are DIAGNOSTICS only. Projection,
 *   centering, clipping, occlusion, and the final `canvas.click({position})`
 *   target are computed from `canvas.getBoundingClientRect()` CSS dimensions.
 *   DPR 1 and DPR 2 must produce byte-identical local/page CSS coordinates and
 *   identical integrity outcomes — proved by `DPR_INVARiance` unit probes.
 *
 * Why exactly-one-click (design JD-DES-002):
 *   Each intended selection has exactly one helper interaction attempt and one
 *   plain `canvas.click({ position })` with no `force`. Helper retries and
 *   Playwright test retries are both `0`; a missing/wrong ficha request or
 *   identity after the single click is FINAL — no second click rescues it.
 *
 * W6 — operator auth + distinct cache identity + silent-refresh bearer (D10):
 *   The pure contracts below model the token lifecycle (seed -> optional
 *   observed refresh -> rotated), the exact-bearer rule for every rainfall
 *   request kind (scope/analysis/series/CSV/XLSX), and the fail-closed cache
 *   isolation rules (RMEH-006, RMEH-013). The W7/W8 spec layer wires the actual
 *   `page.route` handlers using these pure contracts; nothing here touches
 *   Playwright or an application store, and no real credential ever enters.
 */

// --------------------------------------------------------------------------- //
// Types — strict, parsed from `unknown`; no `any`, no direct union
// --------------------------------------------------------------------------- //
import fixtureJsonDefault from '../fixtures/rainfall-multi-parcel.fixture.json';

export const PARCEL_ALIAS = { A: 'A', B: 'B', C: 'C' } as const;
export type ParcelAlias = (typeof PARCEL_ALIAS)[keyof typeof PARCEL_ALIAS];

export interface LngLat {
  lng: number;
  lat: number;
}

export interface GeoJsonPolygon {
  type: 'Polygon';
  coordinates: number[][][]; // [ring][vertex][lng, lat]
}

export interface FixtureProvenance {
  sourcePath: string;
  sourceFeatureId: string;
  sourceGeometrySha256: string;
  derivation: 'exact-ring-extraction';
}

export interface RainfallFixture {
  scopeKind: 'zone' | 'basin';
  scopeId: string;
  scopeVersion: string;
  effectiveCacheKey: string;
  percentile: number;
  accumulationMm: number;
  analysisRevisionId: string;
  dataRevision: string;
  metricRevision: string;
  ready?: boolean;
}

export interface ParcelFixture {
  alias: ParcelAlias;
  stableUuid: string;
  nomenclature: string;
  displayIdentity: string;
  geometry: GeoJsonPolygon;
  interiorPoint: LngLat;
  provenance: FixtureProvenance;
  rainfall: RainfallFixture;
}

export interface Viewport {
  width: number;
  height: number;
  sheetStage?: 'medio' | 'alto' | 'bajo';
}

export interface Camera {
  lat: number;
  lng: number;
  zoom: number;
  viewport: Viewport;
  metersPerPixel?: number;
}

export interface RectCss {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface HarnessFixture {
  schemaVersion: number;
  change: string;
  description: string;
  sourceDataset: {
    path: string;
    features: number;
    derivationScript: string;
  };
  cameras: { mobile: Camera; desktop: Camera };
  coveringZone: {
    kind: 'fixture-zone';
    id: string;
    nomenclature: string;
    geometry: GeoJsonPolygon;
    covers: ParcelAlias[];
  };
  coveringSoil: {
    kind: 'fixture-soil';
    id: string;
    nomenclature: string;
    simbolo: string;
    cap: string;
    ip: number;
    haSuelo: number;
    geometry: GeoJsonPolygon;
    intersects: ParcelAlias[];
  };
  parcels: ParcelFixture[];
  geometryChecks: Record<string, number>;
}

// --------------------------------------------------------------------------- //
// Projection constants (design §Camera and Projection Algorithm)
// --------------------------------------------------------------------------- //
export const TILE_SIZE_PX = 512;
export const MIN_EDGE_CLEARANCE_PX = 12;
export const MIN_DISK_RADIUS_PX = 6;
export const CLICKABLE_DISK_RADIUS_PX = 6;
export const MAX_MERCATOR_LAT = 85.05112878;

// --------------------------------------------------------------------------- //
// Strict validator — no `any`, no A fallback (RMEH-003-A/B/006-A/B/013-A)
// --------------------------------------------------------------------------- //
function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isString(v: unknown, field: string): string {
  if (typeof v !== 'string' || v.length === 0) {
    throw new Error(`fixture invalid: ${field} must be a non-empty string`);
  }
  return v;
}

function isNumber(v: unknown, field: string): number {
  if (typeof v !== 'number' || Number.isNaN(v)) {
    throw new Error(`fixture invalid: ${field} must be a number`);
  }
  return v;
}

function isLngLat(v: unknown, field: string): LngLat {
  if (!isObject(v)) throw new Error(`fixture invalid: ${field} must be an object`);
  return {
    lng: isNumber(v.lng, `${field}.lng`),
    lat: isNumber(v.lat, `${field}.lat`),
  };
}

function isGeoJsonPolygon(v: unknown, field: string): GeoJsonPolygon {
  if (!isObject(v)) throw new Error(`fixture invalid: ${field} must be an object`);
  if (v.type !== 'Polygon') {
    throw new Error(`fixture invalid: ${field}.type must be "Polygon"`);
  }
  const coords = v.coordinates;
  if (!Array.isArray(coords) || coords.length === 0) {
    throw new Error(`fixture invalid: ${field}.coordinates must be a non-empty array`);
  }
  for (const ring of coords) {
    if (!Array.isArray(ring) || ring.length < 4) {
      throw new Error(`fixture invalid: ${field}.coordinates ring must have >= 4 vertices`);
    }
    for (const vertex of ring) {
      if (!Array.isArray(vertex) || vertex.length < 2) {
        throw new Error(`fixture invalid: ${field}.coordinates vertex must be [lng, lat]`);
      }
    }
  }
  return { type: 'Polygon', coordinates: coords as number[][][] };
}

function isProvenance(v: unknown): FixtureProvenance {
  if (!isObject(v)) throw new Error('fixture invalid: provenance must be an object');
  const derivation = v.derivation;
  if (derivation !== 'exact-ring-extraction') {
    throw new Error(`fixture invalid: provenance.derivation must be "exact-ring-extraction"`);
  }
  return {
    sourcePath: isString(v.sourcePath, 'provenance.sourcePath'),
    sourceFeatureId: isString(v.sourceFeatureId, 'provenance.sourceFeatureId'),
    sourceGeometrySha256: isString(v.sourceGeometrySha256, 'provenance.sourceGeometrySha256'),
    derivation,
  };
}

function isRainfall(v: unknown, alias: ParcelAlias): RainfallFixture {
  if (!isObject(v)) throw new Error(`fixture invalid: parcel ${alias}.rainfall must be an object`);
  const scopeKind = v.scopeKind;
  if (scopeKind !== 'zone' && scopeKind !== 'basin') {
    throw new Error(`fixture invalid: parcel ${alias}.rainfall.scopeKind must be "zone" or "basin"`);
  }
  return {
    scopeKind,
    scopeId: isString(v.scopeId, `parcel ${alias}.rainfall.scopeId`),
    scopeVersion: isString(v.scopeVersion, `parcel ${alias}.rainfall.scopeVersion`),
    effectiveCacheKey: isString(
      v.effectiveCacheKey,
      `parcel ${alias}.rainfall.effectiveCacheKey`,
    ),
    percentile: isNumber(v.percentile, `parcel ${alias}.rainfall.percentile`),
    accumulationMm: isNumber(v.accumulationMm, `parcel ${alias}.rainfall.accumulationMm`),
    analysisRevisionId: isString(
      v.analysisRevisionId,
      `parcel ${alias}.rainfall.analysisRevisionId`,
    ),
    dataRevision: isString(v.dataRevision, `parcel ${alias}.rainfall.dataRevision`),
    metricRevision: isString(v.metricRevision, `parcel ${alias}.rainfall.metricRevision`),
    ready: typeof v.ready === 'boolean' ? v.ready : true,
  };
}

function isParcel(v: unknown, idx: number): ParcelFixture {
  if (!isObject(v)) throw new Error(`fixture invalid: parcel[${idx}] must be an object`);
  const alias = v.alias;
  if (alias !== 'A' && alias !== 'B' && alias !== 'C') {
    throw new Error(`fixture invalid: parcel[${idx}].alias must be A, B, or C`);
  }
  return {
    alias,
    stableUuid: isString(v.stableUuid, `parcel ${alias}.stableUuid`),
    nomenclature: isString(v.nomenclature, `parcel ${alias}.nomenclature`),
    displayIdentity: isString(v.displayIdentity, `parcel ${alias}.displayIdentity`),
    geometry: isGeoJsonPolygon(v.geometry, `parcel ${alias}.geometry`),
    interiorPoint: isLngLat(v.interiorPoint, `parcel ${alias}.interiorPoint`),
    provenance: isProvenance(v.provenance),
    rainfall: isRainfall(v.rainfall, alias),
  };
}

const DISTINCT_FIELDS = [
  'stableUuid',
  'nomenclature',
  'displayIdentity',
] as const;

const DISTINCT_RAINFALL_FIELDS = [
  'scopeId',
  'scopeVersion',
  'effectiveCacheKey',
  'percentile',
  'accumulationMm',
  'analysisRevisionId',
  'dataRevision',
  'metricRevision',
] as const;

export function validateFixture(raw: unknown): HarnessFixture {
  if (!isObject(raw)) throw new Error('fixture invalid: root must be an object');
  if (raw.schemaVersion !== 1) {
    throw new Error(`fixture invalid: schemaVersion must be 1`);
  }
  const parcelsRaw = raw.parcels;
  if (!Array.isArray(parcelsRaw) || parcelsRaw.length !== 3) {
    throw new Error(`fixture invalid: cardinality expected exactly 3 parcels`);
  }
  const parcels = parcelsRaw.map((p, i) => isParcel(p, i));
  const aliases = parcels.map((p) => p.alias).sort();
  if (aliases[0] !== 'A' || aliases[1] !== 'B' || aliases[2] !== 'C') {
    throw new Error(`fixture invalid: alias must be one each A/B/C (observed ${aliases.join(',')})`);
  }
  if (new Set(aliases).size !== 3) {
    throw new Error(`fixture invalid: duplicate alias (observed ${aliases.join(',')})`);
  }
  for (const p of parcels) {
    if (!p.rainfall.ready) {
      throw new Error(`fixture invalid: parcel ${p.alias} is not rainfall-ready`);
    }
  }
  // Pairwise distinctness across all A/B/C dimensions.
  for (const f of DISTINCT_FIELDS) {
    const vals = parcels.map((p) => p[f]);
    if (new Set(vals).size !== 3) {
      throw new Error(`fixture invalid: ${f} not pairwise distinct (${vals.join(',')})`);
    }
  }
  for (const f of DISTINCT_RAINFALL_FIELDS) {
    const vals = parcels.map((p) => p.rainfall[f]);
    if (new Set(vals).size !== 3) {
      throw new Error(`fixture invalid: rainfall.${f} not pairwise distinct (cache/scope/revision aliasing)`);
    }
  }
  // Cameras
  const camerasRaw = raw.cameras;
  if (!isObject(camerasRaw) || !isObject(camerasRaw.mobile) || !isObject(camerasRaw.desktop)) {
    throw new Error('fixture invalid: cameras.mobile and cameras.desktop required');
  }
  return raw as unknown as HarnessFixture;
}

export function loadFixture(raw: unknown): HarnessFixture {
  return validateFixture(raw);
}

// --------------------------------------------------------------------------- //
// Web Mercator projection — CSS-space, live-rect-relative (RMEH-003-C/004-A/B)
// --------------------------------------------------------------------------- //
export interface ProjectionDiagnostics {
  devicePixelRatio: number;
  backingStoreWidth: number;
  backingStoreHeight: number;
  rectLeft: number;
  rectTop: number;
  rectWidth: number;
  rectHeight: number;
}

export interface Projection {
  localCssX: number;
  localCssY: number;
  pageCssX: number;
  pageCssY: number;
  integrityOk: boolean;
  diagnostics: ProjectionDiagnostics;
}

export interface ProjectionOptions {
  devicePixelRatio?: number;
}

function clampLat(lat: number): number {
  return Math.max(-MAX_MERCATOR_LAT, Math.min(MAX_MERCATOR_LAT, lat));
}

function mercatorX(lng: number, worldSize: number): number {
  return ((lng + 180) / 360) * worldSize;
}

function mercatorY(lat: number, worldSize: number): number {
  const l = Math.log((1 + Math.sin(lat * Math.PI / 180)) / (1 - Math.sin(lat * Math.PI / 180)));
  return (0.5 - l / (4 * Math.PI)) * worldSize;
}

export function computeProjection(
  target: LngLat,
  camera: Camera,
  rect: RectCss,
  options: ProjectionOptions = {},
): Projection {
  const dpr = options.devicePixelRatio ?? 1;
  const worldSize = TILE_SIZE_PX * 2 ** camera.zoom;
  const clampedLat = clampLat(target.lat);
  const pointX = mercatorX(target.lng, worldSize);
  const pointY = mercatorY(clampedLat, worldSize);
  const cameraX = mercatorX(camera.lng, worldSize);
  const cameraY = mercatorY(clampLat(camera.lat), worldSize);
  // shortest wrapped deltaX across the antimeridian (RMEH-004-A: camera can
  // straddle 180; keep the click on the camera's side of the seam)
  const dxRaw = pointX - cameraX;
  const wrappedDx = ((dxRaw + worldSize / 2) % worldSize + worldSize) % worldSize - worldSize / 2;
  const localCssX = rect.width / 2 + wrappedDx;
  const localCssY = rect.height / 2 + (pointY - cameraY);
  const pageCssX = rect.left + localCssX;
  const pageCssY = rect.top + localCssY;
  // Integrity: the local target must be inside the canvas rectangle.
  const integrityOk =
    localCssX >= 0 && localCssX <= rect.width && localCssY >= 0 && localCssY <= rect.height;
  return {
    localCssX,
    localCssY,
    pageCssX,
    pageCssY,
    integrityOk,
    diagnostics: {
      devicePixelRatio: dpr,
      backingStoreWidth: rect.width * dpr,
      backingStoreHeight: rect.height * dpr,
      rectLeft: rect.left,
      rectTop: rect.top,
      rectWidth: rect.width,
      rectHeight: rect.height,
    },
  };
}

// --------------------------------------------------------------------------- //
// Point-in-polygon (ray casting) + per-parcel projection w/ clearance
// --------------------------------------------------------------------------- //
export function pointInPolygon(point: LngLat, polygon: GeoJsonPolygon): boolean {
  const ring = polygon.coordinates[0];
  const x = point.lng;
  const y = point.lat;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0];
    const yi = ring[i][1];
    const xj = ring[j][0];
    const yj = ring[j][1];
    const crosses = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi || 1e-12) + xi;
    if (crosses) inside = !inside;
  }
  return inside;
}

export interface ParcelProjection {
  localCssX: number;
  localCssY: number;
  pageCssX: number;
  pageCssY: number;
  clearancePx: number;
  diskRadiusPx: number;
  insideOwnPolygon: boolean;
}

function metresPerPixel(lat: number, zoom: number): number {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom;
}

function metresToBoundaryM(point: LngLat, polygon: GeoJsonPolygon): number {
  const ring = polygon.coordinates[0];
  const slat = 110574;
  const slon = 111320 * Math.cos((point.lat * Math.PI) / 180);
  const px = point.lng * slon;
  const py = point.lat * slat;
  let minD = Infinity;
  for (let i = 0; i < ring.length - 1; i++) {
    const ax = ring[i][0] * slon;
    const ay = ring[i][1] * slat;
    const bx = ring[i + 1][0] * slon;
    const by = ring[i + 1][1] * slat;
    const dx = bx - ax;
    const dy = by - ay;
    const lsq = dx * dx + dy * dy;
    const t = lsq === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / lsq));
    const qx = ax + t * dx;
    const qy = ay + t * dy;
    const d = Math.hypot(px - qx, py - qy);
    if (d < minD) minD = d;
  }
  return minD;
}

export function projectParcel(
  parcel: ParcelFixture,
  camera: Camera,
  rect: RectCss,
): ParcelProjection {
  const proj = computeProjection(parcel.interiorPoint, camera, rect);
  const clearanceM = metresToBoundaryM(parcel.interiorPoint, parcel.geometry);
  const mpp = camera.metersPerPixel ?? metresPerPixel(camera.lat, camera.zoom);
  return {
    localCssX: proj.localCssX,
    localCssY: proj.localCssY,
    pageCssX: proj.pageCssX,
    pageCssY: proj.pageCssY,
    clearancePx: clearanceM / mpp,
    diskRadiusPx: Math.min(clearanceM / mpp, CLICKABLE_DISK_RADIUS_PX * 4),
    insideOwnPolygon: pointInPolygon(parcel.interiorPoint, parcel.geometry),
  };
}

// --------------------------------------------------------------------------- //
// Occlusion denylist — ficha sheet, marker/popup, controls (RMEH-003-C/004-B)
// --------------------------------------------------------------------------- //
export interface OccludingRect {
  x: number;
  y: number;
  w: number;
  h: number;
  tags: string[];
}

export const OCCLUSION_DENYLIST_TAGS = [
  'ficha-sheet',
  'maplibregl-marker',
  'maplibregl-popup',
  'maplibregl-ctrl-nav',
  'maplibregl-ctrl-fullscreen',
  'maplibregl-ctrl-scale',
  'pointer-intercept',
];

export interface OcclusionFn {
  isOccluded(point: { x: number; y: number }): boolean;
}

export function occlusion(rects: OccludingRect[]): OcclusionFn {
  return {
    isOccluded(point) {
      for (const r of rects) {
        if (point.x >= r.x && point.x <= r.x + r.w && point.y >= r.y && point.y <= r.y + r.h) {
          if (r.tags.some((t) => OCCLUSION_DENYLIST_TAGS.includes(t))) return true;
        }
      }
      return false;
    },
  };
}

// --------------------------------------------------------------------------- //
// Exactly-one-click interaction policy + forbidden seam (RMEH-005-A/B/C)
// --------------------------------------------------------------------------- //
export const FORBIDDEN_SEAM_PATTERNS = [
  'force:true',
  'direct-store-mutation',
  'fixed-click-pixel',
  'scale-label-wait',
  'production-hook',
  'production-route',
  'production-property',
  'reload-between-selections',
  'multi-select',
  'queryRenderedFeatures',
] as const;

export const INTERACTION_POLICY = {
  clicksPerSelection: 1,
  attemptsPerSelection: 1,
  helperRetries: 0,
  playwrightRetries: 0,
} as const;

export interface Conformance {
  clicks: number;
  attempts: number;
  helperRetries: number;
  playwrightRetries: number;
  requestObserved: boolean;
  identityMatches: boolean;
  forbiddenSeams: string[];
}

export function assertConformanceValid(c: Conformance): void {
  if (c.forbiddenSeams.length > 0) {
    throw new Error(`forbidden seam invalidated conformance: ${c.forbiddenSeams.join(', ')}`);
  }
  if (c.clicks !== 1) {
    throw new Error(`exactly one click required (observed ${c.clicks})`);
  }
  if (c.attempts !== INTERACTION_POLICY.attemptsPerSelection) {
    throw new Error(`exactly one attempt required (observed ${c.attempts})`);
  }
  if (c.helperRetries !== INTERACTION_POLICY.helperRetries) {
    throw new Error(`helper retries must be 0 (observed ${c.helperRetries})`);
  }
  if (c.playwrightRetries !== INTERACTION_POLICY.playwrightRetries) {
    throw new Error(`Playwright retries must be 0 (observed ${c.playwrightRetries})`);
  }
  if (!c.requestObserved) {
    throw new Error('click produced no ficha POST request (tipo=parcela expected)');
  }
  if (!c.identityMatches) {
    throw new Error('rendered identity does not match the click target (stale or aliased cache)');
  }
}

export function redactedConformanceFailure(c: Conformance): string {
  // No secrets in the failure message; only the structural conformance facts.
  return JSON.stringify({
    clicks: c.clicks,
    attempts: c.attempts,
    helperRetries: c.helperRetries,
    playwrightRetries: c.playwrightRetries,
    requestObserved: c.requestObserved,
    identityMatches: c.identityMatches,
    forbiddenSeams: c.forbiddenSeams,
  });
}

// --------------------------------------------------------------------------- //
// Cameras export (re-exported from a validated fixture for default use)
// --------------------------------------------------------------------------- //
export const CAMERAS = validateFixture(fixtureJsonDefault).cameras;

// --------------------------------------------------------------------------- //
// W6 — operator auth + distinct cache identity + silent-refresh bearer (D10)
// --------------------------------------------------------------------------- //
// Pure contracts only. The W7/W8 spec layer wires `page.route` handlers from
// these; no Playwright type or application-store import lives in this file.
// --------------------------------------------------------------------------- //

/** Token lifecycle: `seed token -> optional observed refresh -> rotated token`. */
export interface TokenLifecycle {
  seedToken: string;
  rotatedToken: string;
  refreshed: boolean;
}

export function makeTokenLifecycle(seedToken: string, rotatedToken: string): TokenLifecycle {
  return { seedToken, rotatedToken, refreshed: false };
}

/** The token active for the current sequence: seed until a refresh is observed. */
export function activeToken(lifecycle: TokenLifecycle): string {
  return lifecycle.refreshed ? lifecycle.rotatedToken : lifecycle.seedToken;
}

/** Returns a NEW lifecycle with the refresh observed (immutable). */
export function observeRefresh(lifecycle: TokenLifecycle): TokenLifecycle {
  return { ...lifecycle, refreshed: true };
}

/** Deterministic silent-refresh route contract (one rotated synthetic token). */
export function refreshRouteContract(lifecycle: TokenLifecycle): {
  path: string;
  status: number;
  body: { access_token: string };
} {
  return {
    path: '/auth/jwt/refresh',
    status: 200,
    body: { access_token: lifecycle.rotatedToken },
  };
}

/** One observed rainfall request — the trace record the spec layer attaches. */
export interface RainfallRequestRecord {
  kind: 'scope-resolve' | 'analysis' | 'series' | 'csv' | 'xlsx';
  method: 'GET' | 'POST';
  url: string;
  headers: Record<string, string>;
}

/**
 * Classify a rainfall request from its method + URL into the five kinds the
 * boundary owns (RMEH-006). Purely syntactic: no body inspection, no store.
 */
export function classifyRainfallRequest(
  method: 'GET' | 'POST',
  url: string,
  headers: Record<string, string>,
): RainfallRequestRecord {
  let kind: RainfallRequestRecord['kind'];
  if (method === 'POST' && url.includes('scopes:resolve')) {
    kind = 'scope-resolve';
  } else if (url.endsWith('.csv')) {
    kind = 'csv';
  } else if (url.endsWith('.xlsx')) {
    kind = 'xlsx';
  } else if (url.endsWith('/series')) {
    kind = 'series';
  } else {
    kind = 'analysis';
  }
  return { kind, method, url, headers };
}

/**
 * Exact-bearer rule (D10): the request MUST carry `Authorization: Bearer
 * <activeToken>` and the token MUST NOT appear in the URL. Any other header
 * (missing, stale, wrong scheme, bare token) or a URL credential fails closed.
 */
export function assertExactBearer(record: RainfallRequestRecord, token: string): void {
  const auth = record.headers.authorization ?? record.headers.Authorization;
  if (auth !== `Bearer ${token}`) {
    throw new Error(
      `rainfall ${record.kind} request must carry Authorization: Bearer <active synthetic token> (observed ${auth ?? '(missing)'})`,
    );
  }
  if (record.url.includes(token)) {
    throw new Error(`rainfall ${record.kind} token must never appear in the URL`);
  }
}

/**
 * Resolve a scope identity to exactly one fixture parcel. Unknown identity
 * FAILS — there is no A fallback (RMEH-006-B, D10).
 */
export function resolveParcelByIdentity(
  parcels: ParcelFixture[],
  scopeId: string,
): ParcelFixture {
  const match = parcels.find((p) => p.rainfall.scopeId === scopeId);
  if (!match) {
    throw new Error(`unknown rainfall scope identity "${scopeId}" — no A fallback`);
  }
  return match;
}

/** The complete ready contract a parcel's analysis response must satisfy. */
export interface ReadyRainfallContract {
  scopeKind: 'zone' | 'basin';
  scopeId: string;
  scopeVersion: string;
  effectiveCacheKey: string;
  percentile: number;
  accumulationMm: number;
  analysisRevisionId: string;
  dataRevision: string;
  metricRevision: string;
}

/**
 * Build the ready response contract for a parcel from its fixture facts.
 * A non-ready parcel THROWS — queued/error states are never normalized into
 * a ready answer (RMEH-006-B).
 */
export function readyResponseFor(parcel: ParcelFixture): ReadyRainfallContract {
  const r = parcel.rainfall;
  // `ready` is omitted from the committed fixture (absent = ready, matching
  // `isRainfall`'s default); an EXPLICIT `false` is a non-ready fact.
  const ready = r.ready === undefined ? true : r.ready;
  if (!ready) {
    throw new Error(
      `parcel ${parcel.alias} rainfall is not ready — missing/queued/error facts must never be normalized into a ready answer`,
    );
  }
  return {
    scopeKind: r.scopeKind,
    scopeId: r.scopeId,
    scopeVersion: r.scopeVersion,
    effectiveCacheKey: r.effectiveCacheKey,
    percentile: r.percentile,
    accumulationMm: r.accumulationMm,
    analysisRevisionId: r.analysisRevisionId,
    dataRevision: r.dataRevision,
    metricRevision: r.metricRevision,
  };
}

/**
 * All five semantic dimensions of a ready answer must match the TARGET parcel:
 * scope identity, percentile, accumulation, and the analysis+data+metric
 * revision triple. Any stale/aliased/unknown value fails closed (RMEH-006-C,
 * RMEH-013-B).
 */
export function assertResponseMatchesTarget(
  response: ReadyRainfallContract,
  target: ParcelFixture,
): void {
  const want = readyResponseFor(target);
  const dims: Array<[string, unknown, unknown]> = [
    ['scopeKind', response.scopeKind, want.scopeKind],
    ['scopeId', response.scopeId, want.scopeId],
    ['scopeVersion', response.scopeVersion, want.scopeVersion],
    ['effectiveCacheKey', response.effectiveCacheKey, want.effectiveCacheKey],
    ['percentile', response.percentile, want.percentile],
    ['accumulationMm', response.accumulationMm, want.accumulationMm],
    ['analysisRevisionId', response.analysisRevisionId, want.analysisRevisionId],
    ['dataRevision', response.dataRevision, want.dataRevision],
    ['metricRevision', response.metricRevision, want.metricRevision],
  ];
  const mismatched = dims.filter(([, observed, expected]) => observed !== expected);
  if (mismatched.length > 0) {
    throw new Error(
      `stale or aliased facts for target ${target.alias}: ${mismatched
        .map(([name, observed, expected]) => `${name}=${String(observed)} (expected ${String(expected)})`)
        .join(', ')}`,
    );
  }
}

/**
 * Pairwise distinct effective cache keys (RMEH-013-A/C). Any two parcels
 * sharing a key fail closed naming the aliased identities.
 */
export function assertCacheKeysDistinct(parcels: ParcelFixture[]): void {
  const seen = new Map<string, ParcelAlias>();
  for (const p of parcels) {
    const key = p.rainfall.effectiveCacheKey;
    const prior = seen.get(key);
    if (prior !== undefined) {
      throw new Error(
        `cache aliasing: parcels ${prior} and ${p.alias} share effectiveCacheKey "${key}"`,
      );
    }
    seen.set(key, p.alias);
  }
}

/**
 * Freshness gate for a transition: the observed response must be the TARGET's
 * own ready contract and its cache key must map back to the target — one parcel
 * receiving another parcel's cached response fails closed (RMEH-013-B/C).
 */
export function assertFreshResponse(
  observed: ReadyRainfallContract,
  target: ParcelFixture,
  parcels: ParcelFixture[],
): void {
  const owner = parcels.find((p) => p.rainfall.effectiveCacheKey === observed.effectiveCacheKey);
  if (!owner) {
    throw new Error(
      `response cache key "${observed.effectiveCacheKey}" matches no fixture parcel (aliased or unknown cache)`,
    );
  }
  if (owner.alias !== target.alias) {
    throw new Error(
      `stale/aliased cached response: observed ${owner.alias} facts served as ${target.alias} (cache key "${observed.effectiveCacheKey}")`,
    );
  }
  assertResponseMatchesTarget(observed, target);
}