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

import type { Camera, LngLat, RectCss } from '../e2e/helpers/rainfallMultiParcelHarness';
import {
  CAMERAS,
  CLICKABLE_DISK_RADIUS_PX,
  FORBIDDEN_SEAM_PATTERNS,
  INTERACTION_POLICY,
  MIN_EDGE_CLEARANCE_PX,
  MIN_DISK_RADIUS_PX,
  assertConformanceValid,
  computeProjection,
  loadFixture,
  occlusion,
  pointInPolygon,
  projectParcel,
  redactedConformanceFailure,
  validateFixture,
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
    const p = computeProjection({ lng: 0, lat: 0 }, { lat: 0, lng: 0, zoom: 0 }, rect);
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
    const p = computeProjection({ lng: 180, lat: 0 }, { lat: 0, lng: 0, zoom: 0 }, rect);
    expect(Math.abs(p.localCssX - rect.width / 2)).toBeLessThanOrEqual(256);
    // The non-wrapped page coordinate still maps to the antimeridian.
    expect(p.pageCssX).toBeGreaterThanOrEqual(0);
    expect(p.pageCssX).toBeLessThanOrEqual(rect.width);
  });

  it('clamps to Web Mercator max latitude (~85.05112878) without throwing', () => {
    const rect: RectCss = { left: 0, top: 0, width: 512, height: 512 };
    expect(() =>
      computeProjection({ lng: 0, lat: 89 }, { lat: 0, lng: 0, zoom: 0 }, rect),
    ).not.toThrow();
    const p = computeProjection({ lng: 0, lat: 89 }, { lat: 0, lng: 0, zoom: 0 }, rect);
    const pClamped = computeProjection({ lng: 0, lat: 85.05112878 }, { lat: 0, lng: 0, zoom: 0 }, rect);
    expect(p.localCssY).toBeCloseTo(pClamped.localCssY, 3);
  });

  it('applies non-zero rect.left/top to pageCss but localCss is rect-relative only', () => {
    const rect: RectCss = { left: 240, top: 80, width: 390, height: 844 };
    const p = computeProjection({ lng: 0, lat: 0 }, { lat: 0, lng: 0, zoom: 0 }, rect);
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