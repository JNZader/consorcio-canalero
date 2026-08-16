/**
 * rainfallMultiParcelHarness.test.ts — RED tests for W2.2/W2.3/W2.4 of change
 * `rainfall-multi-parcel-e2e-harness`.
 *
 * Pure Vitest, NO Playwright runtime. Exercises the pure helper at
 * `tests/e2e/helpers/rainfallMultiParcelHarness.ts`:
 *  - W2.2 strict `unknown` parsing + cardinality/distinctness + ready contract
 *    (RMEH-003-A/B, RMEH-006-A/B, RMEH-013-A);
 *  - W2.3 projection/geometry: Web Mercator known points, getBoundingClientRect
 *    with non-zero offsets, DPR 1 vs DPR 2 byte-identical CSS coords, DPR
 *    diagnostic-only, point-in-polygon, >=12 CSS px edge clearance, 6 CSS px
 *    clickable disk, pairwise non-overlap (disk-vs-disk, disk-vs-other-parcel),
 *    clipping, occlusion denylist (RMEH-003-C, RMEH-004-A/B);
 *  - W2.4 exactly-one-click contract + forbidden-seam denylist (RMEH-005-A/B/C).
 *
 * The acceptance command (from tasks.md) is:
 *   `npx --prefix consorcio-web vitest run tests/unit/rainfallMultiParcelHarness.test.ts`
 * (Repo uses pnpm in tasks but npm/vitest are equivalently valid here.)
 */

import { describe, expect, it } from 'vitest';

import { mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import type {
  Camera,
  DesktopFocusSnapshot,
  LngLat,
  MobileReadyEvidence,
  RainfallRequestRecord,
  RectCss,
  TargetReadyEvidence,
} from '../e2e/helpers/rainfallMultiParcelHarness';
import {
  CAMERAS,
  CLICKABLE_DISK_RADIUS_PX,
  FORBIDDEN_SEAM_PATTERNS,
  INTERACTION_POLICY,
  MIN_EDGE_CLEARANCE_PX,
  MIN_DISK_RADIUS_PX,
  activeToken,
  assertCacheKeysDistinct,
  assertCardContained,
  assertDesktopFocusStable,
  assertExactBearer,
  assertFreshResponse,
  assertMobileReady,
  assertResponseMatchesTarget,
  assertScrollRangeAndWheelProof,
  assertConformanceValid,
  assertTargetReady,
  classifyRainfallRequest,
  computeProjection,
  loadFixture,
  makeTokenLifecycle,
  observeRefresh,
  occlusion,
  pointInPolygon,
  projectParcel,
  readyResponseFor,
  redactedConformanceFailure,
  refreshRouteContract,
  resolveParcelByIdentity,
  scopeSentenceFor,
  validateFixture,
  writeHarnessManifest,
} from '../e2e/helpers/rainfallMultiParcelHarness';

import fixtureJson from '../e2e/fixtures/rainfall-multi-parcel.fixture.json';

// --------------------------------------------------------------------------- //
// W2.2 — strict parse, cardinality exactly 3, pairwise distinct, ready-only
// --------------------------------------------------------------------------- //
describe('W2.2 fixture validator — strict parse + cardinality + distinctness', () => {
  it('parses the committed fixture as exactly three A/B/C parcels', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    expect(fixture.parcels.map((p) => p.alias).sort()).toEqual(['A', 'B', 'C']);
    expect(fixture.parcels).toHaveLength(3);
  });

  it('parses provenance with the exact derivation marker', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    for (const p of fixture.parcels) {
      expect(p.provenance.derivation).toBe('exact-ring-extraction');
      expect(p.provenance.sourcePath).toContain('catastro_rural_cu.geojson');
      expect(p.provenance.sourceGeometrySha256).toMatch(/^[0-9a-f]{64}$/);
    }
  });

  it('rejects a missing field (no A fallback; strict throw)', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    const parcels = bad.parcels as Array<Record<string, unknown>>;
    delete (parcels[0].rainfall as Record<string, unknown>).percentile;
    expect(() => validateFixture(bad as unknown)).toThrow(/percentile|missing|invalid/i);
  });

  it('rejects a non-ready parcel', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    const parcels = bad.parcels as Array<Record<string, unknown>>;
    // Inject a "ready=false" by stuffing a non-ready marker into the rain fact.
    (parcels[0].rainfall as Record<string, unknown>).ready = false;
    expect(() => validateFixture(bad as unknown)).toThrow(/ready/i);
  });

  it('rejects unknown scope kind', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    const parcels = bad.parcels as Array<Record<string, unknown>>;
    (parcels[1].rainfall as Record<string, unknown>).scopeKind = 'planet';
    expect(() => validateFixture(bad as unknown)).toThrow(/scope/i);
  });

  it('rejects cardinality != 3', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    (bad.parcels as unknown[]).pop();
    expect(() => validateFixture(bad as unknown)).toThrow(/cardinality|expected exactly 3/i);
  });

  it('rejects duplicate alias', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    const parcels = bad.parcels as Array<Record<string, unknown>>;
    parcels[2].alias = 'A';
    expect(() => validateFixture(bad as unknown)).toThrow(/alias/i);
  });

  it('requires pairwise distinct identity/scope/percentile/accumulation/revision/cache', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    const parcelStringFields = ['stableUuid', 'nomenclature', 'displayIdentity'] as const;
    const rainfallFields = [
      'scopeId',
      'scopeVersion',
      'effectiveCacheKey',
      'percentile',
      'accumulationMm',
      'analysisRevisionId',
      'dataRevision',
      'metricRevision',
    ] as const;
    for (const f of parcelStringFields) {
      const vals = fixture.parcels.map((p) => p[f] as string);
      expect(new Set(vals).size).toBe(3);
    }
    for (const f of rainfallFields) {
      const vals = fixture.parcels.map((p) => p.rainfall[f] as string | number);
      expect(new Set(vals).size).toBe(3);
    }
  });

  it('rejects a swapped cache key (aliasing across parcels)', () => {
    const bad = JSON.parse(JSON.stringify(fixtureJson)) as Record<string, unknown>;
    const parcels = bad.parcels as Array<Record<string, unknown>>;
    const aKey = (parcels[0].rainfall as Record<string, unknown>).effectiveCacheKey;
    (parcels[0].rainfall as Record<string, unknown>).effectiveCacheKey = (
      parcels[1].rainfall as Record<string, unknown>
    ).effectiveCacheKey;
    (parcels[1].rainfall as Record<string, unknown>).effectiveCacheKey = aKey;
    // Even after swapping, distinctness holds — but cache-key cardinality must
    // remain exactly 3. A duplicate (not a swap) must fail.
    (parcels[1].rainfall as Record<string, unknown>).effectiveCacheKey = (
      parcels[2].rainfall as Record<string, unknown>
    ).effectiveCacheKey;
    expect(() => validateFixture(bad as unknown)).toThrow(/cache|distinct/i);
  });

  it('loads the fixture via the helper loader with the same contract', () => {
    const fixture = loadFixture(fixtureJson as unknown);
    expect(fixture.parcels).toHaveLength(3);
    expect(fixture.cameras.mobile.zoom).toBe(fixture.cameras.desktop.zoom);
  });
});

// --------------------------------------------------------------------------- //
// W2.3 — projection / geometry / occlusion
// --------------------------------------------------------------------------- //
describe('W2.3 projection — Web Mercator, DPR-invariant CSS coords, geometry', () => {
  it('projects a known lng/lat at zoom 0 to the world half-extent', () => {
    // Web Mercator world size at tile-size 512, zoom 0: 512 px. Center is
    // (0,0) -> x=256, y=256. lng=0, lat=0 -> (256, 256).
    const rect: RectCss = { left: 0, top: 0, width: 512, height: 512 };
    const camera: Camera = { lat: 0, lng: 0, zoom: 0, viewport: { width: 512, height: 512 } };
    const p = computeProjection({ lng: 0, lat: 0 }, camera, rect);
    expect(p.localCssX).toBeCloseTo(256, 5);
    expect(p.localCssY).toBeCloseTo(256, 5);
    expect(p.pageCssX).toBeCloseTo(256, 5);
    expect(p.pageCssY).toBeCloseTo(256, 5);
  });

  it('projects lng=180 at zoom 0 symmetrically to the antimeridian edge (wrapped)', () => {
    // At camera=(0,0), zoom 0, worldSize=512. lng=180 projects to x=512 (the
    // right edge) but it is exactly at the antimeridian: it is ALSO lng=-180,
    // which projects to x=0 (the left edge). Our wrap keeps the click on the
    // camera's side, so the wrapped localCssX lands within [-256, +256] of the
    // canvas center — i.e. clamped to the visible half-world centered on the
    // camera. Assert the wrap is symmetric: |localCssX - rect.width/2| <= 256.
    const rect: RectCss = { left: 0, top: 0, width: 512, height: 512 };
    const camera: Camera = { lat: 0, lng: 0, zoom: 0, viewport: { width: 512, height: 512 } };
    const p = computeProjection({ lng: 180, lat: 0 }, camera, rect);
    expect(Math.abs(p.localCssX - rect.width / 2)).toBeLessThanOrEqual(256);
    // The non-wrapped page coordinate still maps to the antimeridian.
    expect(p.pageCssX).toBeGreaterThanOrEqual(0);
    expect(p.pageCssX).toBeLessThanOrEqual(rect.width);
  });

  it('clamps to Web Mercator max latitude (~85.05112878) without throwing', () => {
    const rect: RectCss = { left: 0, top: 0, width: 512, height: 512 };
    const camera: Camera = { lat: 0, lng: 0, zoom: 0, viewport: { width: 512, height: 512 } };
    expect(() =>
      computeProjection({ lng: 0, lat: 89 }, camera, rect),
    ).not.toThrow();
    const p = computeProjection({ lng: 0, lat: 89 }, camera, rect);
    const pClamped = computeProjection({ lng: 0, lat: 85.05112878 }, camera, rect);
    expect(p.localCssY).toBeCloseTo(pClamped.localCssY, 3);
  });

  it('applies non-zero rect.left/top to pageCss but localCss is rect-relative only', () => {
    const rect: RectCss = { left: 240, top: 80, width: 390, height: 844 };
    const camera: Camera = { lat: 0, lng: 0, zoom: 0, viewport: { width: 390, height: 844 } };
    const p = computeProjection({ lng: 0, lat: 0 }, camera, rect);
    expect(p.localCssX).toBeCloseTo(rect.width / 2, 5);
    expect(p.localCssY).toBeCloseTo(rect.height / 2, 5);
    expect(p.pageCssX).toBeCloseTo(rect.left + rect.width / 2, 5);
    expect(p.pageCssY).toBeCloseTo(rect.top + rect.height / 2, 5);
  });

  it('is byte-identical at DPR 1 vs DPR 2 — local/page CSS coords and integrity', () => {
    // design JD-DES-001: DPR/backing-store are diagnostics only, never an input.
    const rect: RectCss = { left: 100, top: 200, width: 390, height: 844 };
    const camera = CAMERAS.mobile;
    const target: LngLat = { lng: -62.49285, lat: -32.51034 };
    const dpr1 = computeProjection(target, camera, rect, { devicePixelRatio: 1 });
    const dpr2 = computeProjection(target, camera, rect, { devicePixelRatio: 2 });
    expect(dpr1.localCssX).toBe(dpr2.localCssX);
    expect(dpr1.localCssY).toBe(dpr2.localCssY);
    expect(dpr1.pageCssX).toBe(dpr2.pageCssX);
    expect(dpr1.pageCssY).toBe(dpr2.pageCssY);
    expect(dpr1.integrityOk).toBe(dpr2.integrityOk);
    // Diagnostics capture the DPR/backing dimensions but do NOT affect the
    // coords: localCssX/Y are pure functions of rect + camera + target.
    expect(dpr1.diagnostics.devicePixelRatio).toBe(1);
    expect(dpr2.diagnostics.devicePixelRatio).toBe(2);
  });

  it('contains a target point inside its parcel polygon (point-in-polygon)', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    for (const p of fixture.parcels) {
      expect(pointInPolygon(p.interiorPoint, p.geometry)).toBe(true);
    }
  });

  it('rejects a point outside the polygon', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    const a = fixture.parcels[0];
    // A point obviously east of every parcel ring vertex.
    const outside: LngLat = { lng: a.geometry.coordinates[0][0][0] + 5, lat: a.interiorPoint.lat };
    expect(pointInPolygon(outside, a.geometry)).toBe(false);
  });

  it('projects each parcel into the mobile viewport with >= 12 CSS px edge clearance', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    const rect: RectCss = { left: 0, top: 0, width: CAMERAS.mobile.viewport.width, height: CAMERAS.mobile.viewport.height };
    for (const p of fixture.parcels) {
      const proj = projectParcel(p, CAMERAS.mobile, rect);
      expect(proj.clearancePx).toBeGreaterThanOrEqual(MIN_EDGE_CLEARANCE_PX);
      expect(proj.diskRadiusPx).toBeGreaterThanOrEqual(MIN_DISK_RADIUS_PX);
    }
  });

  it('projects each parcel into the desktop viewport with the same clearance', () => {
    const fixture = validateFixture(fixtureJson as unknown);
    const rect: RectCss = { left: 0, top: 0, width: CAMERAS.desktop.viewport.width, height: CAMERAS.desktop.viewport.height };
    for (const p of fixture.parcels) {
      const proj = projectParcel(p, CAMERAS.desktop, rect);
      expect(proj.clearancePx).toBeGreaterThanOrEqual(MIN_EDGE_CLEARANCE_PX);
      expect(proj.diskRadiusPx).toBeGreaterThanOrEqual(MIN_DISK_RADIUS_PX);
    }
  });

  it('the three clickable disks are pairwise non-overlapping (>= 2*radius)', () => {
    const fixtures = validateFixture(fixtureJson as unknown);
    const rect: RectCss = { left: 0, top: 0, width: CAMERAS.mobile.viewport.width, height: CAMERAS.mobile.viewport.height };
    const projections = fixtures.parcels.map((p) => projectParcel(p, CAMERAS.mobile, rect));
    for (let i = 0; i < 3; i++) {
      for (let j = i + 1; j < 3; j++) {
        const dx = projections[i].localCssX - projections[j].localCssX;
        const dy = projections[i].localCssY - projections[j].localCssY;
        const dist = Math.hypot(dx, dy);
        expect(dist).toBeGreaterThan(2 * CLICKABLE_DISK_RADIUS_PX);
      }
    }
  });

  it('no disk is contained inside another parcel projected polygon', () => {
    const fixtures = validateFixture(fixtureJson as unknown);
    const rect: RectCss = { left: 0, top: 0, width: CAMERAS.mobile.viewport.width, height: CAMERAS.mobile.viewport.height };
    for (const target of fixtures.parcels) {
      const t = projectParcel(target, CAMERAS.mobile, rect);
      const targetCenterLngLat: LngLat = {
        lng: unprojectX(t.localCssX, CAMERAS.mobile, rect),
        lat: unprojectY(t.localCssY, CAMERAS.mobile, rect),
      };
      for (const other of fixtures.parcels) {
        if (other.alias === target.alias) continue;
        expect(pointInPolygon(targetCenterLngLat, other.geometry)).toBe(false);
      }
    }
  });

  it('occlusion denylist flags the ficha sheet, marker/popup, and the nav/fullscreen/scale controls', () => {
    const deny = occlusion([
      { x: 100, y: 600, w: 390, h: 244, tags: ['ficha-sheet'] },
      { x: 195, y: 400, w: 30, h: 30, tags: ['maplibregl-marker'] },
      { x: 0, y: 0, w: 30, h: 30, tags: ['maplibregl-ctrl-nav'] },
      { x: 350, y: 0, w: 30, h: 30, tags: ['maplibregl-ctrl-fullscreen'] },
      { x: 0, y: 700, w: 60, h: 20, tags: ['maplibregl-ctrl-scale'] },
    ]);
    expect(deny.isOccluded({ x: 195, y: 400 })).toBe(true);
    expect(deny.isOccluded({ x: 100, y: 700 })).toBe(true);
    expect(deny.isOccluded({ x: 200, y: 300 })).toBe(false);
  });
});

function unprojectX(localCssX: number, camera: Camera, rect: RectCss): number {
  // Inverse of computeProjection x: lng = (localCssX - rect.width/2)/worldSize * 360 + camera.lng
  const worldSize = 512 * 2 ** camera.zoom;
  return ((localCssX - rect.width / 2) / worldSize) * 360 + camera.lng;
}
function unprojectY(localCssY: number, camera: Camera, rect: RectCss): number {
  const worldSize = 512 * 2 ** camera.zoom;
  const y = localCssY - rect.height / 2;
  // Inverse Web Mercator y: lat = atan(sinh(pi * (1 - 2 * y / worldSize)))
  const n = Math.PI - (2 * Math.PI * y) / worldSize;
  return Math.atan(Math.sinh(n)) * (180 / Math.PI) + camera.lat;
}

// --------------------------------------------------------------------------- //
// W2.4 — exactly-one-click contract + forbidden-seam denylist
// --------------------------------------------------------------------------- //
describe('W2.4 interaction policy — exactly one click, zero retries, no forbidden seam', () => {
  it('requires exactly one click and one attempt per selection', () => {
    expect(INTERACTION_POLICY.helperRetries).toBe(0);
    expect(INTERACTION_POLICY.playwrightRetries).toBe(0);
    expect(INTERACTION_POLICY.clicksPerSelection).toBe(1);
    expect(INTERACTION_POLICY.attemptsPerSelection).toBe(1);
  });

  it('forbids force-click, store mutation, fixed pixels, scale wait, hooks, reload, multi-select, queryRenderedFeatures', () => {
    const forbidden = FORBIDDEN_SEAM_PATTERNS;
    expect(forbidden).toContain('force:true');
    expect(forbidden).toContain('direct-store-mutation');
    expect(forbidden).toContain('fixed-click-pixel');
    expect(forbidden).toContain('scale-label-wait');
    expect(forbidden).toContain('production-hook');
    expect(forbidden).toContain('production-route');
    expect(forbidden).toContain('production-property');
    expect(forbidden).toContain('reload-between-selections');
    expect(forbidden).toContain('multi-select');
    expect(forbidden).toContain('queryRenderedFeatures');
  });

  it('assertConformanceValid accepts exactly one click + correct identity', () => {
    const conformance = {
      clicks: 1,
      attempts: 1,
      helperRetries: 0,
      playwrightRetries: 0,
      requestObserved: true,
      identityMatches: true,
      forbiddenSeams: [],
    };
    expect(() => assertConformanceValid(conformance)).not.toThrow();
  });

  it('assertConformanceValid rejects force:true', () => {
    expect(() =>
      assertConformanceValid({
        clicks: 1,
        attempts: 1,
        helperRetries: 0,
        playwrightRetries: 0,
        requestObserved: true,
        identityMatches: true,
        forbiddenSeams: ['force:true'],
      }),
    ).toThrow(/forbidden|seam/i);
  });

  it('assertConformanceValid rejects two clicks (a hidden retry)', () => {
    expect(() =>
      assertConformanceValid({
        clicks: 2,
        attempts: 1,
        helperRetries: 0,
        playwrightRetries: 0,
        requestObserved: true,
        identityMatches: true,
        forbiddenSeams: [],
      }),
    ).toThrow(/click|exactly one/i);
  });

  it('assertConformanceValid rejects a helper retry > 0', () => {
    expect(() =>
      assertConformanceValid({
        clicks: 1,
        attempts: 2,
        helperRetries: 1,
        playwrightRetries: 0,
        requestObserved: true,
        identityMatches: true,
        forbiddenSeams: [],
      }),
    ).toThrow(/retry|attempt/i);
  });

  it('assertConformanceValid rejects a missing request (click without ficha POST)', () => {
    expect(() =>
      assertConformanceValid({
        clicks: 1,
        attempts: 1,
        helperRetries: 0,
        playwrightRetries: 0,
        requestObserved: false,
        identityMatches: false,
        forbiddenSeams: [],
      }),
    ).toThrow(/request|ficha|tipo/i);
  });

  it('assertConformanceValid rejects a wrong identity (stale/aliased cache)', () => {
    expect(() =>
      assertConformanceValid({
        clicks: 1,
        attempts: 1,
        helperRetries: 0,
        playwrightRetries: 0,
        requestObserved: true,
        identityMatches: false,
        forbiddenSeams: [],
      }),
    ).toThrow(/identity/i);
  });

  it('redactedConformanceFailure omits secrets and clips forbidden-seam evidence', () => {
    const msg = redactedConformanceFailure({
      clicks: 2,
      attempts: 1,
      helperRetries: 0,
      playwrightRetries: 0,
      requestObserved: true,
      identityMatches: false,
      forbiddenSeams: ['force:true', 'direct-store-mutation'],
    });
    expect(msg).toContain('force:true');
    expect(msg).not.toContain('Bearer');
    expect(msg).not.toContain('password');
  });
});

// --------------------------------------------------------------------------- //
// W6.2 — exact silent-refresh bearer (RMEH-006-A/B/C, RMEH-013-A, D10)
// --------------------------------------------------------------------------- //
describe('W6.2 auth — exact bearer, token lifecycle, ready-only responses', () => {
  const fixture = loadFixture(fixtureJson as unknown);
  const A = fixture.parcels.find((p) => p.alias === 'A')!;
  const B = fixture.parcels.find((p) => p.alias === 'B')!;

  const SEED = 'rmeh-seed-token-1';
  const ROTATED = 'rmeh-rotated-token-2';

  it('activeToken is the seed before any refresh and the rotated token after', () => {
    const lc = makeTokenLifecycle(SEED, ROTATED);
    expect(activeToken(lc)).toBe(SEED);
    const after = observeRefresh(lc);
    expect(activeToken(after)).toBe(ROTATED);
    // observeRefresh is immutable — the original lifecycle still holds the seed.
    expect(activeToken(lc)).toBe(SEED);
  });

  it('refreshRouteContract returns one deterministic rotated synthetic token', () => {
    const lc = makeTokenLifecycle(SEED, ROTATED);
    const contract = refreshRouteContract(lc);
    expect(contract.path).toContain('/auth/jwt/refresh');
    expect(contract.status).toBe(200);
    expect(contract.body).toEqual({ access_token: ROTATED });
  });

  it('every rainfall request kind must carry the exact active bearer in the header', () => {
    const lc = makeTokenLifecycle(SEED, ROTATED);
    for (const kind of ['scope-resolve', 'analysis', 'series', 'csv', 'xlsx'] as const) {
      const record = classifyRainfallRequest(
        kind === 'scope-resolve' || kind === 'analysis' ? 'POST' : 'GET',
        `https://app.local/api/v2/geo/rainfall/${kind === 'scope-resolve' ? 'scopes:resolve' : kind === 'analysis' ? 'analyses' : kind === 'series' ? 'series' : kind === 'csv' ? 'export.csv' : 'export.xlsx'}`,
        { authorization: `Bearer ${activeToken(lc)}` }
      );
      // Exact match passes.
      expect(() => assertExactBearer(record, activeToken(lc))).not.toThrow();
    }
  });

  it('rejects a missing, wrong, or stale bearer (rotated token no longer accepted)', () => {
    const lc = makeTokenLifecycle(SEED, ROTATED);
    const after = observeRefresh(lc);
    const record = classifyRainfallRequest(
      'POST',
      'https://app.local/api/v2/geo/rainfall/analyses',
      { authorization: `Bearer ${SEED}` }
    );
    // After refresh the SEED is stale — exact-bearer must reject it.
    expect(() => assertExactBearer(record, activeToken(after))).toThrow(/bearer|authorization/i);
    // Missing header.
    const bare = classifyRainfallRequest('POST', 'https://app.local/api/v2/geo/rainfall/analyses', {});
    expect(() => assertExactBearer(bare, activeToken(lc))).toThrow(/bearer|authorization/i);
    // Wrong scheme.
    const wrong = classifyRainfallRequest(
      'POST',
      'https://app.local/api/v2/geo/rainfall/analyses',
      { authorization: `Token ${SEED}` }
    );
    expect(() => assertExactBearer(wrong, activeToken(lc))).toThrow(/bearer|authorization/i);
  });

  it('rejects a token leaked into the URL', () => {
    const lc = makeTokenLifecycle(SEED, ROTATED);
    const leaked = classifyRainfallRequest(
      'GET',
      `https://app.local/api/v2/geo/rainfall/export.csv?access_token=${SEED}`,
      { authorization: `Bearer ${SEED}` }
    );
    expect(() => assertExactBearer(leaked, activeToken(lc))).toThrow(/url/i);
  });

  it('unknown identity fails the route — no A fallback', () => {
    expect(() => resolveParcelByIdentity(fixture.parcels, 'zone:not-in-fixture:v9')).toThrow(
      /unknown|identity/i
    );
  });

  it('readyResponseFor builds a complete ready contract matching the parcel facts', () => {
    const contract = readyResponseFor(A);
    expect(contract).toEqual({
      scopeKind: A.rainfall.scopeKind,
      scopeId: A.rainfall.scopeId,
      scopeVersion: A.rainfall.scopeVersion,
      effectiveCacheKey: A.rainfall.effectiveCacheKey,
      percentile: A.rainfall.percentile,
      accumulationMm: A.rainfall.accumulationMm,
      analysisRevisionId: A.rainfall.analysisRevisionId,
      dataRevision: A.rainfall.dataRevision,
      metricRevision: A.rainfall.metricRevision,
    });
  });

  it('refuses a non-ready parcel — no queued/error normalization into ready', () => {
    const notReady = { ...A, rainfall: { ...A.rainfall, ready: false } };
    expect(() => readyResponseFor(notReady)).toThrow(/not ready|queued|error/i);
  });

  it('assertResponseMatchesTarget passes only when all five dimensions match the target', () => {
    expect(() => assertResponseMatchesTarget(readyResponseFor(A), A)).not.toThrow();
    // B's ready response must NOT pass for target A (stale/aliased facts).
    expect(() => assertResponseMatchesTarget(readyResponseFor(B), A)).toThrow(
      /stale|aliased|expected/i
    );
  });

  it('a request trace observer records every rainfall kind with its headers', () => {
    const trace: RainfallRequestRecord[] = [];
    trace.push(
      classifyRainfallRequest('POST', 'https://app.local/api/v2/geo/rainfall/analyses', {
        authorization: `Bearer ${SEED}`,
      }),
      classifyRainfallRequest('GET', 'https://app.local/api/v2/geo/rainfall/export.csv', {
        authorization: `Bearer ${SEED}`,
      })
    );
    expect(trace.map((r) => r.kind)).toEqual(['analysis', 'csv']);
    expect(trace.every((r) => r.headers.authorization === `Bearer ${SEED}`)).toBe(true);
    // No secret is ever recorded into the URL field by classification.
    expect(trace.every((r) => !r.url.includes(SEED))).toBe(true);
  });
});

// --------------------------------------------------------------------------- //
// W6.3 — cache-aliasing negatives (RMEH-013-A/B/C)
// --------------------------------------------------------------------------- //
describe('W6.3 cache identity — aliasing fails closed with diagnostics', () => {
  const fixture = loadFixture(fixtureJson as unknown);
  const A = fixture.parcels.find((p) => p.alias === 'A')!;
  const B = fixture.parcels.find((p) => p.alias === 'B')!;
  const C = fixture.parcels.find((p) => p.alias === 'C')!;

  it('assertCacheKeysDistinct accepts the committed fixture (pairwise distinct)', () => {
    expect(() => assertCacheKeysDistinct(fixture.parcels)).not.toThrow();
  });

  it('two parcels sharing an effective cache key fail closed with diagnostics', () => {
    const aliased = [A, { ...B, rainfall: { ...B.rainfall, effectiveCacheKey: A.rainfall.effectiveCacheKey } }];
    expect(() => assertCacheKeysDistinct(aliased)).toThrow(/aliasing|effectiveCacheKey|A|B/i);
  });

  it('one parcel receiving another parcel cached response fails freshness', () => {
    // B's request answered from A's cached contract → must fail closed naming the alias.
    expect(() =>
      assertFreshResponse(readyResponseFor(A), B, fixture.parcels)
    ).toThrow(/cached|aliased|A|B/i);
  });

  it('an A-only value remaining current after B/C selection fails the transition', () => {
    // Simulate B ready but a stale A percentile still displayed (RMEH-013-B).
    const staleB = {
      ...readyResponseFor(B),
      percentile: A.rainfall.percentile,
      accumulationMm: A.rainfall.accumulationMm,
    };
    expect(() => assertResponseMatchesTarget(staleB, B)).toThrow(/stale|aliased|expected/i);
    // And a full A contract must not pass as a fresh B answer.
    expect(() => assertResponseMatchesTarget(readyResponseFor(A), B)).toThrow(
      /stale|aliased|expected/i
    );
  });

  it('fresh A after C requires the exact A revision, not a stale C or aliased cache', () => {
    // A's own ready contract passes for A…
    expect(() => assertResponseMatchesTarget(readyResponseFor(A), A)).not.toThrow();
    // …but C's contract presented as fresh A fails (stale C facts).
    expect(() => assertResponseMatchesTarget(readyResponseFor(C), A)).toThrow(
      /stale|aliased|expected/i
    );
    // And an aliased A key answered with B's scope/revision fails closed.
    const aliasedA = { ...readyResponseFor(A), scopeId: B.rainfall.scopeId, metricRevision: B.rainfall.metricRevision };
    expect(() => assertResponseMatchesTarget(aliasedA, A)).toThrow(/stale|aliased|expected/i);
  });
});

// --------------------------------------------------------------------------- //
// W7.1–W7.3 — mobile A→B→C→A state machine contracts (RMEH-007, RMEH-005)
// --------------------------------------------------------------------------- //
describe('W7 mobile state machine — ready assertion, scroll proof, containment', () => {
  const fixture = loadFixture(fixtureJson as unknown);
  const A = fixture.parcels.find((p) => p.alias === 'A')!;
  const B = fixture.parcels.find((p) => p.alias === 'B')!;
  const C = fixture.parcels.find((p) => p.alias === 'C')!;

  const SEED = 'rmeh-seed-token-1';
  const lc = makeTokenLifecycle(SEED, 'rmeh-rotated-token-2');

  function readyEvidence(overrides: Partial<TargetReadyEvidence> = {}): TargetReadyEvidence {
    return {
      targetAlias: 'A',
      lluviaSelected: true,
      renderedIdentity: A.nomenclature,
      renderedScopeSentence: scopeSentenceFor(A),
      renderedPercentile: A.rainfall.percentile,
      renderedAccumulationMm: A.rainfall.accumulationMm,
      renderedMetricRevision: A.rainfall.metricRevision,
      traces: {
        scopeNomenclature: A.nomenclature,
        analysisCacheKey: A.rainfall.effectiveCacheKey,
        seriesScopeId: A.rainfall.scopeId,
      },
      analysisSequence: 2,
      previous: null,
      activeToken: activeToken(lc),
      authHeader: `Bearer ${activeToken(lc)}`,
      tokenInUrl: false,
      ...overrides,
    };
  }

  it('assertTargetReady accepts a complete READY_A evidence set', () => {
    expect(() => assertTargetReady(readyEvidence(), A)).not.toThrow();
  });

  it('assertTargetReady requires the Lluvia tab to remain selected', () => {
    expect(() => assertTargetReady(readyEvidence({ lluviaSelected: false }), A)).toThrow(
      /lluvia/i
    );
  });

  it('assertTargetReady rejects a rendered identity mismatch (wrong parcel ficha)', () => {
    expect(() =>
      assertTargetReady(readyEvidence({ renderedIdentity: B.nomenclature }), A)
    ).toThrow(/identity/i);
  });

  it('assertTargetReady rejects stale scope/percentile/accumulation/revision', () => {
    expect(() =>
      assertTargetReady(readyEvidence({ renderedPercentile: B.rainfall.percentile }), A)
    ).toThrow(/percentile|scope|accumulation|revision|stale/i);
    expect(() =>
      assertTargetReady(readyEvidence({ renderedAccumulationMm: B.rainfall.accumulationMm }), A)
    ).toThrow(/accumulation|percentile|revision|stale/i);
    expect(() =>
      assertTargetReady(readyEvidence({ renderedMetricRevision: B.rainfall.metricRevision }), A)
    ).toThrow(/revision|stale/i);
  });

  it('assertTargetReady requires the traces to belong to the target', () => {
    expect(() =>
      assertTargetReady(readyEvidence({ traces: { ...readyEvidence().traces, analysisCacheKey: B.rainfall.effectiveCacheKey } }), A)
    ).toThrow(/cache|scope|trace/i);
    expect(() =>
      assertTargetReady(readyEvidence({ traces: { ...readyEvidence().traces, scopeNomenclature: B.nomenclature } }), A)
    ).toThrow(/trace|scope|identity/i);
  });

  it('assertTargetReady fails when the bearer is missing, stale, or in the URL', () => {
    expect(() => assertTargetReady(readyEvidence({ authHeader: 'Bearer wrong-token' }), A)).toThrow(
      /bearer|authorization/i
    );
    expect(() => assertTargetReady(readyEvidence({ authHeader: '(missing)' }), A)).toThrow(
      /bearer|authorization/i
    );
    expect(() => assertTargetReady(readyEvidence({ tokenInUrl: true }), A)).toThrow(/url/i);
  });

  it('assertTargetReady rejects a previous-only value remaining current (RMEH-013-B)', () => {
    // previous = B: its percentile must NOT remain current as the A answer.
    expect(() =>
      assertTargetReady(
        readyEvidence({
          previous: {
            renderedPercentile: B.rainfall.percentile,
            renderedAccumulationMm: B.rainfall.accumulationMm,
            renderedMetricRevision: B.rainfall.metricRevision,
            analysisSequence: 1,
          },
          renderedPercentile: B.rainfall.percentile,
        }),
        A
      )
    ).toThrow(/previous|stale|percentile/i);
  });

  it('assertTargetReady rejects a response that is not newer than the previous target (stale cache)', () => {
    expect(() =>
      assertTargetReady(
        readyEvidence({
          previous: {
            renderedPercentile: B.rainfall.percentile,
            renderedAccumulationMm: B.rainfall.accumulationMm,
            renderedMetricRevision: B.rainfall.metricRevision,
            analysisSequence: 3,
          },
          analysisSequence: 2, // same-or-older sequence than the prior target
        }),
        A
      )
    ).toThrow(/sequence|newer|stale/i);
  });

  it('scopeSentenceFor derives the exact scope sentence from fixture facts', () => {
    // The DOM sentence is kind label + prettified id — NOT the raw composite
    // scopeId. Only a LEADING kind-repeating token is dropped (app rule:
    // `index > 0` keeps later tokens), so "rmeh-zone-a" yields "la zona Rmeh
    // Zone A". The oracle must reproduce the app rule so a presentation drift
    // fails the journey instead of passing it.
    expect(scopeSentenceFor(A)).toBe('la zona Rmeh Zone A');
    expect(scopeSentenceFor(B)).toBe('la zona Rmeh Zone B');
    expect(scopeSentenceFor(C)).toBe('la zona Rmeh Zone C');
  });

  it('assertScrollRangeAndWheelProof accepts a real wheel proof', () => {
    expect(() =>
      assertScrollRangeAndWheelProof({
        range: 320,
        intendedDelta: 320,
        beforeScrollTop: 0,
        afterWheelScrollTop: 128,
      })
    ).not.toThrow();
  });

  it('assertScrollRangeAndWheelProof rejects a zero range (scrollHeight <= clientHeight)', () => {
    expect(() =>
      assertScrollRangeAndWheelProof({
        range: 0,
        intendedDelta: 0,
        beforeScrollTop: 0,
        afterWheelScrollTop: 0,
      })
    ).toThrow(/scrollHeight|clientHeight|range/i);
  });

  it('assertScrollRangeAndWheelProof rejects a wheel that did not move (afterWheelScrollTop <= 0)', () => {
    expect(() =>
      assertScrollRangeAndWheelProof({
        range: 320,
        intendedDelta: 320,
        beforeScrollTop: 0,
        afterWheelScrollTop: 0,
      })
    ).toThrow(/afterWheelScrollTop|scroll/i);
  });

  it('assertScrollRangeAndWheelProof rejects an intended delta that is not the range (direct assignment)', () => {
    expect(() =>
      assertScrollRangeAndWheelProof({
        range: 320,
        intendedDelta: 64, // not scrollHeight - clientHeight → not the real wheel path
        beforeScrollTop: 0,
        afterWheelScrollTop: 64,
      })
    ).toThrow(/delta|range/i);
  });

  it('assertCardContained accepts a card fully inside the sheet body', () => {
    expect(() =>
      assertCardContained(
        { left: 12, top: 200, width: 366, height: 300 },
        { left: 0, top: 0, width: 390, height: 844 }
      )
    ).not.toThrow();
  });

  it('assertCardContained rejects a card overflowing the visible body (±1 CSS px)', () => {
    expect(() =>
      assertCardContained(
        { left: 12, top: 500, width: 366, height: 400 },
        { left: 0, top: 0, width: 390, height: 844 }
      )
    ).toThrow(/contain|visible|body/i);
  });

  it('assertMobileReady requires stage=medio, scrollTop=0 and containment', () => {
    const base = readyEvidence();
    const mobile: MobileReadyEvidence = {
      ...base,
      stage: 'medio',
      scrollTopAfter: 0,
      cardBox: { left: 12, top: 200, width: 366, height: 300 },
      bodyBox: { left: 0, top: 0, width: 390, height: 844 },
    };
    expect(() => assertMobileReady(mobile, A)).not.toThrow();
    expect(() => assertMobileReady({ ...mobile, stage: 'alto' }, A)).toThrow(/medio/i);
    expect(() => assertMobileReady({ ...mobile, scrollTopAfter: 12 }, A)).toThrow(/scrollTop/i);
    expect(() =>
      assertMobileReady({ ...mobile, cardBox: { left: 12, top: 500, width: 366, height: 400 } }, A)
    ).toThrow(/contain|visible|body/i);
  });
});

// --------------------------------------------------------------------------- //
// W8.2 — desktop focus continuity contracts (RMEH-008-B)
// --------------------------------------------------------------------------- //
describe('W8 desktop focus — stable focus allowlist, no mobile geometry', () => {
  it('assertDesktopFocusStable accepts body focus', () => {
    expect(() =>
      assertDesktopFocusStable({
        tagName: 'BODY',
        isBody: true,
        isCanvas: false,
        isMapInteractionAncestor: false,
        intersectsViewport: true,
        hidden: false,
        inert: false,
        disabled: false,
        mobileOnly: false,
      })
    ).not.toThrow();
  });

  it('assertDesktopFocusStable accepts the map canvas', () => {
    expect(() =>
      assertDesktopFocusStable({
        tagName: 'CANVAS',
        isBody: false,
        isCanvas: true,
        isMapInteractionAncestor: false,
        intersectsViewport: true,
        hidden: false,
        inert: false,
        disabled: false,
        mobileOnly: false,
      })
    ).not.toThrow();
  });

  it('assertDesktopFocusStable accepts a visible map interaction ancestor', () => {
    expect(() =>
      assertDesktopFocusStable({
        tagName: 'DIV',
        isBody: false,
        isCanvas: false,
        isMapInteractionAncestor: true,
        intersectsViewport: true,
        hidden: false,
        inert: false,
        disabled: false,
        mobileOnly: false,
      })
    ).not.toThrow();
  });

  it('assertDesktopFocusStable rejects an unrelated, hidden, inert, disabled or mobile-only element', () => {
    const base: DesktopFocusSnapshot = {
      tagName: 'BUTTON',
      isBody: false,
      isCanvas: false,
      isMapInteractionAncestor: false,
      intersectsViewport: true,
      hidden: false,
      inert: false,
      disabled: false,
      mobileOnly: false,
    };
    expect(() => assertDesktopFocusStable(base)).toThrow(/body|canvas|ancestor/i);
    expect(() => assertDesktopFocusStable({ ...base, isMapInteractionAncestor: true, hidden: true })).toThrow(/hidden|inert|disabled|mobile/i);
    expect(() => assertDesktopFocusStable({ ...base, isMapInteractionAncestor: true, inert: true })).toThrow(/hidden|inert|disabled|mobile/i);
    expect(() => assertDesktopFocusStable({ ...base, isMapInteractionAncestor: true, disabled: true })).toThrow(/hidden|inert|disabled|mobile/i);
    expect(() => assertDesktopFocusStable({ ...base, isMapInteractionAncestor: true, mobileOnly: true })).toThrow(/hidden|inert|disabled|mobile/i);
  });

  it('assertDesktopFocusStable rejects a non-body element outside the viewport', () => {
    expect(() =>
      assertDesktopFocusStable({
        tagName: 'DIV',
        isBody: false,
        isCanvas: false,
        isMapInteractionAncestor: true,
        intersectsViewport: false,
        hidden: false,
        inert: false,
        disabled: false,
        mobileOnly: false,
      })
    ).toThrow(/viewport/i);
  });
});

describe('W9.6 manifest evidence — selection-records contract on disk (A2)', () => {
  it('writeHarnessManifest writes { selection_records } to dirname(outputJson)/manifest.json', () => {
    const dir = mkdtempSync(join(tmpdir(), 'rmeh-manifest-'));
    const outputJson = join(dir, 'nested', 'playwright-results.json');
    const records = [
      {
        context: 'mobile' as const,
        target: 'A' as const,
        attemptCount: 1,
        clickCount: 1,
        wheelProofsBeforeClick: 0,
        analysisSequence: 1,
      },
    ];
    const manifestPath = writeHarnessManifest(records, outputJson);
    expect(manifestPath).toBe(join(dir, 'nested', 'manifest.json'));
    const written = JSON.parse(readFileSync(manifestPath, 'utf8')) as {
      selection_records: unknown[];
    };
    expect(Array.isArray(written.selection_records)).toBe(true);
    expect(written.selection_records).toHaveLength(1);
  });

  it('writeHarnessManifest round-trips the exact fields the driver gate reads', () => {
    const dir = mkdtempSync(join(tmpdir(), 'rmeh-manifest2-'));
    const records = [
      {
        context: 'desktop' as const,
        target: 'C' as const,
        attemptCount: 1,
        clickCount: 1,
        wheelProofsBeforeClick: 2,
        analysisSequence: 2,
      },
      {
        context: 'mobile' as const,
        target: 'B' as const,
        attemptCount: 2,
        clickCount: 1,
        wheelProofsBeforeClick: 0,
        analysisSequence: 3,
      },
    ];
    writeHarnessManifest(records, join(dir, 'playwright-results.json'));
    const written = JSON.parse(readFileSync(join(dir, 'manifest.json'), 'utf8')) as {
      selection_records: Array<{
        context: string;
        target: string;
        attemptCount: number;
        clickCount: number;
        wheelProofsBeforeClick: number;
        analysisSequence: number;
      }>;
    };
    expect(written.selection_records.map((r) => r.target)).toEqual(['C', 'B']);
    expect(written.selection_records.map((r) => r.context)).toEqual(['desktop', 'mobile']);
    expect(written.selection_records.map((r) => r.analysisSequence)).toEqual([2, 3]);
  });
});