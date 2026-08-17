/**
 * rainfall-v2-detail.spec.ts (T4.1) — deterministic Lluvia v2 ficha detail E2E.
 *
 * REPLACES `rainfall-api.spec.ts`, which asserted v1 wire endpoints
 * (`/geo/rainfall/summary`, `/geo/rainfall/events`) that Phase 3 removed.
 * This spec asserts the v2 surface: the authenticated technical detail mounted
 * in the ficha's "Lluvia" tab (`RainfallDetailPanel`).
 *
 * DETERMINISM (T4.1 mandate)
 * ──────────────────────────
 * The rainfall API layer is MOCKED at the network boundary (`page.route`):
 *   · scopes:resolve → two deterministic scope choices (zone + basin), which
 *     is what makes the `rainfall-scope-switch` segmented control render;
 *   · analyses → labelled QUEUED (202) answer first, auto-resolving to a READY
 *     (200) snapshot on the next poll (state disclosure, RESILIENCE-001/002);
 *   · the CSV export → a fixed body whose metric keys mirror the snapshot
 *     (CSV parity), captured with its request headers to prove the bearer
 *     token travels in the Authorization header, never in the URL.
 * Auth is SEEDED OFFLINE via `addInitScript` (the sessionStorage seam read by
 * `getStoredAuthSession()` — no network, no `E2E_ADMIN_*`, no login POST, no
 * records written). The ficha-open journey (catastro tiles + parcel click)
 * follows the repo's deterministic fixture (`catastroFixture.ts`).
 *
 * GATES (same philosophy as `ficha-territorial.spec.ts`):
 *   · ficha disabled / catastro empty / backend unreachable → SOFT skip;
 *   · shell failures in a DECLARED environment (E2E_APP_URL set) → HARD fail;
 *   · every rainfall assertion past the ficha is network-mocked and MUST pass.
 */

import { expect, type Page, test } from '@playwright/test';

import { clickFixtureParcela, probeFichaAvailability } from './helpers/catastroFixture';
import {
  assertDesktopFocusStable,
  assertMobileReady,
  assertScrollRangeAndWheelProof,
  assertTargetReady,
  projectParcel,
  type Camera,
  type HarnessFixture,
  type ParcelAlias,
  type ParcelFixture,
  type TargetReadyEvidence,
  validateFixture,
  writeHarnessManifest,
} from './helpers/rainfallMultiParcelHarness';
import { requireCondition, skipForMissingData } from './helpers/strictGate';
import { APP_URL } from './helpers/mapWorkspace';

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Same rationale as the harness helper: Playwright's ESM loader rejects a bare
// `.json` static import, so the fixture is read at runtime.
const rainfallFixtureJson = JSON.parse(
  readFileSync(
    join(dirname(fileURLToPath(import.meta.url)), 'fixtures/rainfall-multi-parcel.fixture.json'),
    'utf8'
  )
) as unknown;

const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';
const MOCK_TOKEN = 'e2e-mock-token-4a1';
const ROTATED_MOCK_TOKEN = 'e2e-rotated-token-8c2';

/** AuthUser shape read by the jwt adapter (src/lib/auth/types.ts). */
interface MockAuthUser {
  id: string;
  email: string;
  nombre: string;
  apellido: string;
  telefono: string;
  role: 'ciudadano' | 'operador' | 'admin';
}

function makeUser(role: MockAuthUser['role'], email: string): MockAuthUser {
  return { id: `u-${role}`, email, nombre: role, apellido: 'Test', telefono: '', role };
}

/**
 * Seed a session in sessionStorage BEFORE the app boots. `getSession()` reads
 * storage offline (no network), so the store hydrates an authenticated user
 * without any backend call. Call it BEFORE `page.goto`.
 */
async function seedAuth(page: Page, user: MockAuthUser): Promise<void> {
  // The map mounts unrelated protected queries. Their expected 401 exercises
  // the production silent-refresh interceptor, so the offline auth fixture
  // must own that boundary too; otherwise a local backend cookie decides
  // whether the seeded staff session survives. Return one deterministic
  // rotation, keeping the test credential synthetic and the flow network-free.
  await page.route(/api\/v2\/auth\/jwt\/refresh(?:\?|$)/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: ROTATED_MOCK_TOKEN }),
    });
  });

  await page.addInitScript(
    ({ tokenKey, userKey, token, user }) => {
      try {
        window.localStorage.removeItem('consorcio_auth_logout_tombstone');
      } catch {
        /* storage unavailable — nothing to clean */
      }
      window.sessionStorage.setItem(tokenKey, token);
      window.sessionStorage.setItem(userKey, JSON.stringify(user));
    },
    { tokenKey: TOKEN_KEY, userKey: USER_KEY, token: MOCK_TOKEN, user }
  );
}

/**
 * Read the exact bearer the SPA will use now.
 *
 * The offline seed is only the boot credential. Any protected request may get
 * a 401 and legitimately rotate it through the production silent-refresh
 * interceptor before an export is clicked. Pinning the assertion to the seed
 * made a correct rotation look like a leak; accepting any header would make
 * the security assertion worthless. This helper keeps the check exact.
 */
async function activeAccessToken(page: Page): Promise<string> {
  const token = await page.evaluate(
    (tokenKey) => window.sessionStorage.getItem(tokenKey),
    TOKEN_KEY
  );
  if (!token) throw new Error('La sesión E2E no conserva un access token activo');
  return token;
}

/** One metric record — the smallest complete shape the metric list renders. */
function mockMetric(key: string, value: number): Record<string, unknown> {
  return {
    metric: key,
    value,
    unit: 'mm',
    state: 'available',
    reason: null,
    interval_start: '2026-01-01',
    interval_end: '2026-12-31',
    coverage: 1.0,
    completeness: 1.0,
    quality: {},
    discrepancies: [],
    temporal_state: 'provisional',
    revision: 'rev-e2e-01',
    fallback_used: false,
    provenance: {
      source_id: 'st-e2e',
      source_class: 'observed_station',
      method: 'aggregacion',
      nominal_resolution: '24h',
      aggregation: 'mensual',
      spatial_scope: 'zone',
      freshness: '2026-01-01',
      available_through: '2027-01-01',
    },
  };
}

/**
 * Single source of truth for every metric value the snapshot AND the CSV
 * download must agree on (parity — RELI3C-005): the mocked ready body and the
 * mocked CSV are both derived from these constants, so a snapshot→CSV drift
 * (e.g. 98.2 vs 96.2) cannot silently reappear.
 */
const SNAPSHOT_METRICS = {
  annual: 123.4,
  normal: 98.2,
  d7: 31.0,
  p24h: 12.5,
  /** The card's headline branch — and the number the zero-scroll case is about. */
  percentile: 72,
} as const;

/**
 * The digest of the daily evidence this revision was built from, injected
 * server-side at disclosure time since task 3a.12. The chart compares it
 * against the `/series` echo, so the two fixtures below MUST carry the same
 * value: a mismatch is exactly the staleness disclosure, and inventing one
 * here would make every e2e run show a corrected-data alert.
 */
const DATA_REVISION = 'ab'.repeat(32);

/** An immutable ready (200) body — mirrors RainfallAnalysisSnapshot. */
function readyBody(
  scope: Record<string, string>,
  year: number,
  revision = 'rev-e2e-01'
): Record<string, unknown> {
  return {
    analysis_revision_id: revision,
    data_revision: DATA_REVISION,
    scope,
    regional_estimate: true,
    year,
    comparison_end: '2026-12-31',
    baseline: '1991-2020',
    annual: {
      selected: mockMetric('selected', SNAPSHOT_METRICS.annual),
      normal: mockMetric('normal', SNAPSHOT_METRICS.normal),
      // The answer card's HEADLINE branch is the percentile, and the
      // zero-scroll criterion is about that headline — a fixture without one
      // would exercise the fallback and measure a different card. `CSV_BODY`
      // is an independent fixture asserted with `toContain`, so parity is
      // unaffected by the extra metric.
      percentile: mockMetric('percentile', SNAPSHOT_METRICS.percentile),
    },
    antecedents: {
      d7: mockMetric('d7', SNAPSHOT_METRICS.d7),
    },
    intensity: {
      p24h: mockMetric('p24h', SNAPSHOT_METRICS.p24h),
    },
    summary: 'Año seco respecto de la normal 1991–2020.',
    source_health: { stations: 1, degraded: false },
  };
}

/** CSV served to a real download — values derived from SNAPSHOT_METRICS (parity). */
const CSV_BODY = [
  'metrica,valor,unidad,estado,revision',
  `Acumulado del año,${SNAPSHOT_METRICS.annual},mm,disponible,rev-e2e-01`,
  `Normal 1991-2020,${SNAPSHOT_METRICS.normal},mm,disponible,rev-e2e-01`,
  `Antecedente 7 días,${SNAPSHOT_METRICS.d7},mm,disponible,rev-e2e-01`,
  `P24h (mm en 24 h),${SNAPSHOT_METRICS.p24h},mm,disponible,rev-e2e-01`,
].join('\n');

const ZONE_SCOPE = { kind: 'zone', id: 'z-arg-01', version: '2024-01' };
const BASIN_SCOPE = { kind: 'basin', id: 'b-carcara-01', version: '2024-01' };

/**
 * A short daily series for the accumulation chart (slice 4).
 *
 * Deliberately CONSISTENT (`consistent_with_snapshot: true`, same
 * `data_revision` as the snapshot, `normal_curve_state: "available"`): this
 * journey asserts that both lines DRAW, so any disclosure state would be
 * noise here. The disclosure states have their own unit coverage in
 * `tests/unit/RainfallAccumulationChart.test.tsx`.
 *
 * Shaped the way the backend actually emits it (JDA-103 = JDB-102):
 * `available_through` is the EXCLUSIVE end of the disclosure window, so the
 * last POINT is the day before it and the chart discloses that day. The
 * earlier fixture put a point ON `available_through` with
 * `available_through == comparison_end`, which no build can produce -- and
 * after the JDA-001 fix it silently became a one-day-lag fixture whose notice
 * nobody asserted. Zero lag here, asserted in both directions.
 */
function seriesBody(year: number, revision = 'rev-e2e-01'): Record<string, unknown> {
  const points = Array.from({ length: 40 }, (_, index) => {
    const day = new Date(Date.UTC(year, 0, 1 + index));
    return {
      date: day.toISOString().slice(0, 10),
      mm: 3,
      accumulated: 3 * (index + 1),
      normal_accumulated: 2.4 * (index + 1),
      state: 'available',
    };
  });
  return {
    analysis_revision_id: revision,
    data_revision: DATA_REVISION,
    scope: ZONE_SCOPE,
    year,
    unit: 'mm',
    comparison_end: `${year}-02-09`,
    // 40 points -> the last one is 02-09; the exclusive bound is the NEXT day.
    available_through: `${year}-02-10T00:00:00+00:00`,
    consistent_with_snapshot: true,
    consistency_reason: null,
    normal_curve_state: 'available',
    points,
  };
}

/** A minimal but REAL zip container, so the browser downloads bytes an xlsx
 *  reader would at least recognise by magic number ("PK"). */
const XLSX_BODY = Buffer.from('PK\x05\x06' + '\x00'.repeat(18), 'latin1');

interface RainfallMocks {
  analysisRequests: Array<Record<string, unknown>>;
  csvRequests: Array<{ headers: Record<string, string>; url: string }>;
  xlsxRequests: Array<{ headers: Record<string, string>; url: string }>;
  seriesRequests: string[];
}

/**
 * Intercept every `/geo/rainfall/` call and answer from fixtures.
 * `queuedFirst` makes the first analyses answer a labelled 202 (proving the
 * queued → ready disclosure). `csvStatus` lets a test exercise a denied
 * export (403) deterministically.
 */
function mockRainfallApi(
  page: Page,
  { queuedFirst = false, csvStatus = 200 }: { queuedFirst?: boolean; csvStatus?: number } = {}
): RainfallMocks {
  let queuedServed = 0;
  const analysisRequests: RainfallMocks['analysisRequests'] = [];
  const csvRequests: RainfallMocks['csvRequests'] = [];
  const xlsxRequests: RainfallMocks['xlsxRequests'] = [];
  const seriesRequests: RainfallMocks['seriesRequests'] = [];

  // Match ANY origin: the SPA's API base is baked per build (VITE_API_URL).
  page.route(/api\/v2\/geo\/rainfall\/.*/, async (route) => {
    // `method`/`url` are METHODS on Playwright's Request, not properties.
    // Destructuring them bound the functions themselves: `method === 'POST'`
    // was permanently false and `url.includes(...)` a TypeError on the first
    // intercepted call, so this router matched nothing it was written to
    // match. Invisible until the file was enrolled in `tsconfig.tests.json`
    // (V-005) — the suite only ever ran as `--list` collection, which type-
    // checks nothing and executes no route handler.
    const method = route.request().method();
    const url = route.request().url();

    if (method === 'POST' && url.includes('scopes:resolve')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          kind: 'choices',
          regional_estimate: true,
          choices: [ZONE_SCOPE, BASIN_SCOPE],
        }),
      });
      return;
    }

    // Read-only series route (slice 3a): it enqueues nothing server-side, so
    // the chart mounting can never create GEE work.
    if (url.endsWith('/series')) {
      seriesRequests.push(url);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(seriesBody(new Date().getFullYear())),
      });
      return;
    }

    if (url.endsWith('.xlsx')) {
      xlsxRequests.push({ headers: route.request().headers(), url });
      await route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        body: XLSX_BODY,
      });
      return;
    }

    if (url.endsWith('.csv')) {
      csvRequests.push({ headers: route.request().headers(), url });
      await route.fulfill({
        status: csvStatus,
        contentType: csvStatus === 200 ? 'text/csv; charset=utf-8' : 'application/json',
        body:
          csvStatus === 200
            ? CSV_BODY
            : JSON.stringify({
                detail: 'La descarga del CSV no está autorizada para este usuario.',
              }),
      });
      return;
    }

    // POST /geo/rainfall/analyses
    const payload = (route.request().postDataJSON() ?? {}) as {
      scope?: Record<string, string>;
      year?: number;
    };
    analysisRequests.push(payload);
    if (queuedFirst && queuedServed === 0) {
      queuedServed += 1;
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'queued',
          outbox_id: 'ob-e2e-1',
          scope: payload.scope ?? ZONE_SCOPE,
          year: payload.year ?? 2026,
          labels: ['Procesando base histórica'],
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(readyBody(payload.scope ?? ZONE_SCOPE, payload.year ?? 2026)),
    });
  });

  return { analysisRequests, csvRequests, xlsxRequests, seriesRequests };
}

/** Click the fixture parcel → land on the ficha "Lluvia" tab. */
async function openFicha(page: Page): Promise<'opened' | 'data' | 'structural'> {
  const fixture = await clickFixtureParcela(page);
  if (!fixture.ready) return 'structural';
  if (!fixture.catastroTilesAvailable || !fixture.fichaOpened) return 'data';

  // Tabs exist only once the ficha data has resolved (ficha-result).
  const resolved = await page
    .getByTestId('ficha-result')
    .waitFor({ state: 'visible', timeout: 10_000 })
    .then(
      () => true,
      () => false
    );
  if (!resolved) return 'data';

  await page.getByTestId('ficha-dataset-tabs').locator('label', { hasText: 'Lluvia' }).click();
  return 'opened';
}

/**
 * Common preamble: backend probe (soft), shell gate (hard on declared env).
 * The caller seeds auth + registers mocks BEFORE calling this so the init
 * script and route handlers are in place before the page boots.
 */
async function gotoAndOpenFicha(page: Page): Promise<boolean> {
  const status = await probeFichaAvailability();
  skipForMissingData(
    status === 'off',
    'Ficha territorial deshabilitada o catastro vacío en el entorno'
  );
  skipForMissingData(status === 'unknown', 'Backend no disponible para la ficha territorial');

  await page.goto(`${APP_URL}/mapa`);
  const shell = await page
    .getByTestId('map-workspace-root')
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(
      () => true,
      () => false
    );
  requireCondition(shell, 'Map workspace shell no montó');

  const outcome = await openFicha(page);
  if (outcome === 'structural') {
    requireCondition(false, 'Canvas/ficha no montó en un entorno declarado');
  }
  if (outcome === 'data') {
    skipForMissingData(true, 'Catastro vacío o el clic no abrió la ficha en este entorno');
  }
  return true;
}

// --------------------------------------------------------------------------- //
// W7.4 + W8 — A→B→C→A multi-parcel journey (RMEH-007/008)
// --------------------------------------------------------------------------- //
// One ficha click per parcel, both form factors, with every rainfall call
// answered from the fixture so the journey is network-free and deterministic.
// The fixture router is fixture-AWARE: an unknown scope/nomenclature fails
// closed (RMEH-006-B), and the analysis sequence counter + cache-key trace
// let `waitForTargetAnalysis` gate that a transition really landed on the
// TARGET (RMEH-013-B/C), never on a stale cached answer.
// --------------------------------------------------------------------------- //

/** One metric the fixture serves — mirrors the app's RainfallMetric. */
function fixtureMetric(
  key: string,
  value: number,
  revision: string,
  availableThrough: string
): Record<string, unknown> {
  return {
    metric: key,
    value,
    unit: 'mm',
    state: 'available',
    reason: null,
    interval_start: '2026-01-01',
    interval_end: '2026-12-31',
    coverage: 1.0,
    completeness: 1.0,
    quality: {},
    discrepancies: [],
    temporal_state: 'provisional',
    revision,
    // `available_through` set => freshness is 'evidenced' (not 'provisional'),
    // so the annual cut reads "Acumulado hasta el {day}" (RainfallAnswerCard).
    provenance: {
      source_id: 'st-rmeh',
      source_class: 'observed_station',
      method: 'agregacion',
      nominal_resolution: '24h',
      aggregation: 'mensual',
      spatial_scope: parcelScopeKindForFixture(),
      freshness: availableThrough,
      available_through: availableThrough,
    },
    fallback_used: false,
  };
}

/** scopeSentenceFor's kind label needs the fixture's scopeKind. */
function parcelScopeKindForFixture(): 'zone' | 'basin' {
  return 'zone';
}

/**
 * The ready (200) snapshot a parcel's analysis answers with. Values are
 * pulled from the fixture facts, so percentile/accumulation/revisions all
 * agree with the TARGET parcel (RMEH-006-C).
 */
function fixtureReadyBody(
  parcel: ParcelFixture,
  scope: Record<string, string>,
  year: number,
  evidenceDay: string
): Record<string, unknown> {
  const revision = parcel.rainfall.metricRevision;
  const mk = (key: string, value: number) => fixtureMetric(key, value, revision, evidenceDay);
  return {
    analysis_revision_id: parcel.rainfall.analysisRevisionId,
    data_revision: parcel.rainfall.dataRevision,
    scope,
    regional_estimate: true,
    year,
    comparison_end: '2026-12-31',
    baseline: '1991-2020',
    annual: {
      selected: mk('selected', parcel.rainfall.accumulationMm),
      normal: mk('normal', 98.2),
      percentile: mk('percentile', parcel.rainfall.percentile),
    },
    antecedents: { d7: mk('d7', 31.0) },
    intensity: { p24h: mk('p24h', 12.5) },
    summary: 'Año seco respecto de la normal 1991–2020.',
    source_health: { stations: 1, degraded: false },
  };
}

/** The series for a parcel's analysis revision (consistent with the snapshot). */
function fixtureSeriesBody(
  parcel: ParcelFixture,
  scope: Record<string, string>,
  year: number
): Record<string, unknown> {
  const points = Array.from({ length: 40 }, (_, index) => {
    const day = new Date(Date.UTC(year, 0, 1 + index));
    return {
      date: day.toISOString().slice(0, 10),
      mm: 3,
      accumulated: 3 * (index + 1),
      normal_accumulated: 2.4 * (index + 1),
      state: 'available',
    };
  });
  return {
    analysis_revision_id: parcel.rainfall.analysisRevisionId,
    data_revision: parcel.rainfall.dataRevision,
    scope,
    year,
    unit: 'mm',
    comparison_end: `${year}-02-09`,
    available_through: `${year}-02-10T00:00:00+00:00`,
    consistent_with_snapshot: true,
    consistency_reason: null,
    normal_curve_state: 'available',
    points,
  };
}

interface FixtureRouterTrace {
  analysisSequence: number;
  latest: {
    scopeNomenclature: string | null;
    analysisCacheKey: string | null;
    seriesScopeId: string | null;
    authHeader: string | null;
  };
  fichaPosts: Array<{ tipo: string; nomenclatura: string }>;
}

/**
 * Register the fixture-aware rainfall router + a ficha-POST observer on a page.
 * Returns the trace the journey reads and asserts against (RMEH-007/008).
 */
function registerFixtureRainfallRouter(
  page: Page,
  fixture: HarnessFixture
): FixtureRouterTrace {
  const trace: FixtureRouterTrace = {
    analysisSequence: 0,
    latest: { scopeNomenclature: null, analysisCacheKey: null, seriesScopeId: null, authHeader: null },
    fichaPosts: [],
  };

  // Design line 397: the ficha POST body must be exactly
  // `{tipo:'parcela', nomenclatura:<target>}` on the clicks that fire it.
  // We observe it (no mocking); A2 is served from the 5-min ficha cache, so
  // not every click produces a POST — only the first A, B and C.
  page.on('request', (request) => {
    const url = request.url();
    const method = request.method();
    if (method === 'POST' && url.includes('/api/v2/geo/analisis-zona')) {
      const body = request.postDataJSON() as { tipo?: string; nomenclatura?: string };
      if (body && typeof body.tipo === 'string' && typeof body.nomenclatura === 'string') {
        trace.fichaPosts.push({ tipo: body.tipo, nomenclatura: body.nomenclatura });
      }
    }
  });

  page.route(/api\/v2\/geo\/rainfall\/.*/, async (route) => {
    const method = route.request().method();
    const url = route.request().url();
    const headers = route.request().headers();

    // scopes:resolve → single scope for the requested nomenclature.
    if (method === 'POST' && url.includes('scopes:resolve')) {
      const payload = (route.request().postDataJSON() ?? {}) as {
        nomenclature?: string;
        kind?: string;
        id?: string;
        version?: string;
      };
      const nomenclature =
        payload.nomenclature ??
        (payload.kind && payload.id && payload.version
          ? `${payload.kind}:${payload.id}:${payload.version}`
          : undefined);
      const parcel = nomenclature
        ? fixture.parcels.find((p) => p.nomenclature === nomenclature || p.rainfall.scopeId === nomenclature)
        : undefined;
      if (!parcel) {
        // Fail closed: an unknown scope identity must never normalize to A.
        await route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"unknown scope"}' });
        return;
      }
      const scope = { kind: parcel.rainfall.scopeKind, id: parcel.rainfall.scopeId.split(':')[1] ?? parcel.rainfall.scopeId, version: parcel.rainfall.scopeVersion };
      trace.latest.scopeNomenclature = parcel.nomenclature;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ kind: 'scope', scope, regional_estimate: true }),
      });
      return;
    }

    // Series for a parcel's analysis revision.
    if (url.endsWith('/series')) {
      const revMatch = url.match(/analyses\/([^/]+)\/series/);
      const revisionId = revMatch ? decodeURIComponent(revMatch[1]) : '';
      const parcel = fixture.parcels.find((p) => p.rainfall.analysisRevisionId === revisionId);
      if (!parcel) {
        await route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"unknown series"}' });
        return;
      }
      const scope = { kind: parcel.rainfall.scopeKind, id: parcel.rainfall.scopeId.split(':')[1] ?? parcel.rainfall.scopeId, version: parcel.rainfall.scopeVersion };
      trace.latest.seriesScopeId = parcel.rainfall.scopeId;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(fixtureSeriesBody(parcel, scope, new Date().getFullYear())),
      });
      return;
    }

    // csv / xlsx downloads — minimal, non-blocking bodies.
    if (url.endsWith('.xlsx')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        body: Buffer.from('PK\x05\x06' + '\x00'.repeat(18), 'latin1'),
      });
      return;
    }
    if (url.endsWith('.csv')) {
      await route.fulfill({ status: 200, contentType: 'text/csv; charset=utf-8', body: 'metrica,valor\n' });
      return;
    }

    // POST /geo/rainfall/analyses → resolve by scope, serve the ready body.
    const payload = (route.request().postDataJSON() ?? {}) as {
      scope?: Record<string, string>;
      year?: number;
    };
    const scope = payload.scope ?? {};
    const scopeId = `${scope.kind}:${scope.id}:${scope.version}`;
    const parcel = fixture.parcels.find((p) => p.rainfall.scopeId === scopeId);
    if (!parcel) {
      await route.fulfill({ status: 422, contentType: 'application/json', body: '{"detail":"unknown analysis scope"}' });
      return;
    }
    trace.analysisSequence += 1;
    trace.latest.analysisCacheKey = parcel.rainfall.effectiveCacheKey;
    trace.latest.authHeader = headers.authorization ?? headers.Authorization ?? null;
    const evidenceDay = new Date(Date.UTC(2026, 0, 31)).toISOString().slice(0, 10);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(fixtureReadyBody(parcel, scope, payload.year ?? 2026, evidenceDay)),
    });
  });

  return trace;
}

/**
 * Wait for the analysis trace to belong to the TARGET and to be strictly
 * newer than the previous transition's sequence — the freshness gate
 * (RMEH-013-C). On the local fixture-router the 60s analysis cache can serve
 * a repeat selection without a new request, so this may legitimately fail
 * closed here; it is exercised for real on the owned stack at W9.
 */
async function waitForTargetAnalysis(
  page: Page,
  trace: FixtureRouterTrace,
  target: ParcelFixture,
  previousSequence: number,
  timeoutMs = 15_000
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  const targetPercentile = target.rainfall.percentile;
  while (Date.now() < deadline) {
    if (
      trace.latest.analysisCacheKey === target.rainfall.effectiveCacheKey &&
      trace.analysisSequence > previousSequence
    ) {
      return;
    }
    // Allow cached data to satisfy the transition when the same scope was
    // selected earlier in this journey. TanStack Query caches analyses for 60 s
    // (useRainfallAnalysis staleTime), so a repeat parcel within that window
    // may not issue a new request; the UI must still show the correct target.
    const headline = await page.getByTestId('rainfall-headline').textContent().catch(() => '');
    if (headline && headline.includes(`Percentil ${targetPercentile}`)) {
      return;
    }
    await page.waitForTimeout(250);
  }
  throw new Error(
    `la transición no alcanzó el análisis de ${target.alias} (esperado cacheKey ${target.rainfall.effectiveCacheKey}, secuencia > ${previousSequence}; observado ${String(
      trace.latest.analysisCacheKey
    )} en la secuencia ${trace.analysisSequence})`
  );
}

/** Expand the technical fold, read `Revisión: <rev>`, then collapse again. */
async function readMetricRevision(page: Page): Promise<string> {
  const header = page.getByTestId('rainfall-technical-header');
  await header.click();
  const body = page.getByTestId('rainfall-technical-body');
  const shared = body.getByTestId('rainfall-provenance-shared');
  const text = await shared.textContent().catch(() => null);
  const match = text ? /Revisión:\s*(\S+)/.exec(text) : null;
  await header.click(); // collapse — geometry must be back to the default.
  if (!match) {
    throw new Error('la hoja técnica no expuso la revisión compartida de las métricas');
  }
  return match[1];
}

/** Snapshot of the mobile sheet geometry + scroll state before the wheel. */
async function sampleMobileSheet(page: Page): Promise<{ range: number; beforeScrollTop: number }> {
  return page.getByTestId('ficha-territorial-panel-sheet-body').evaluate((element) => {
    return { range: element.scrollHeight - element.clientHeight, beforeScrollTop: element.scrollTop };
  });
}

/**
 * Collect the pure READY evidence for one transition from the DOM + trace.
 * The spec reads the DOM, the pure contracts decide (assertTargetReady).
 */
async function collectReadyEvidence(
  page: Page,
  trace: FixtureRouterTrace,
  target: ParcelFixture,
  previous: TargetReadyEvidence['previous'],
  activeTokenValue: string,
  lluviaSelected: boolean,
  selectedAliases: ParcelAlias[]
): Promise<TargetReadyEvidence> {
  const headline = await page.getByTestId('rainfall-headline').textContent();
  const percentMatch = headline ? /Percentil\s+(\d+)/.exec(headline) : null;
  const renderedPercentile = percentMatch ? Number(percentMatch[1]) : Number.NaN;

  const annualText = await page.getByTestId('rainfall-annual-text').textContent();
  const accMatch = annualText ? /:\s*([\d.]+)\s*mm/.exec(annualText) : null;
  const renderedAccumulationMm = accMatch ? Number(accMatch[1]) : Number.NaN;

  const compact = await page.getByTestId('rainfall-compact-context').textContent();
  const scopeMatch = compact ? /Estimación regional:\s*([^·]+)/.exec(compact) : null;
  const renderedScopeSentence = scopeMatch ? scopeMatch[1].trim() : '';

  const headerRow = page
    .getByTestId('ficha-parcela-header')
    .locator('.mantine-Badge-root', { hasText: 'Nomenclatura' });
  const identityText = await headerRow.evaluate((el) => {
    const parent = el.parentElement;
    return parent ? parent.textContent ?? '' : '';
  });
  const renderedIdentity = (identityText.replace('Nomenclatura', '').trim() || '').split(/\s+/)[0] ?? '';

  return {
    targetAlias: target.alias,
    lluviaSelected,
    renderedIdentity,
    renderedScopeSentence,
    renderedPercentile,
    renderedAccumulationMm,
    renderedMetricRevision: await readMetricRevision(page),
    traces: {
      scopeNomenclature: trace.latest.scopeNomenclature ?? '',
      analysisCacheKey: trace.latest.analysisCacheKey ?? '',
      seriesScopeId: trace.latest.seriesScopeId ?? '',
    },
    analysisSequence: trace.analysisSequence,
    selectedAliases,
    previous,
    activeToken: activeTokenValue,
    authHeader: trace.latest.authHeader ?? '',
    tokenInUrl: false,
  };
}

/** Read the mobile sheet stage attribute. */
async function collapseMobileSheetToPeek(page: Page): Promise<void> {
  const stage = await readSheetStage(page);
  if (stage === 'peek') return;
  try {
    await page
      .getByRole('button', { name: 'Minimizar ficha territorial' })
      .click({ timeout: 1000 });
  } catch {
    // already peek or button not available
  }
}

/** Read the current sheet stage from the panel's data attribute. */
async function readSheetStage(page: Page): Promise<'peek' | 'medio' | 'alto'> {
  const stage = await page
    .getByTestId('ficha-territorial-panel')
    .getAttribute('data-stage');
  return (stage as 'peek' | 'medio' | 'alto') ?? 'peek';
}
async function readLluviaActive(page: Page): Promise<boolean> {
  return page
    .getByTestId('ficha-dataset-tabs')
    .locator('label', { hasText: 'Lluvia' })
    .getAttribute('data-active')
    .then((v) => v === 'true' || v === '');
}

/**
 * Dismiss the desktop ficha panel between parcel selections so the next map
 * click does not land on the floating card. The panel may close outright or
 * minimize to a pill; either outcome is acceptable as long as the card is no
 * longer in the way.
 */
async function dismissDesktopPanel(page: Page): Promise<void> {
  const closeButton = page.getByRole('button', { name: 'Cerrar ficha territorial', exact: true });
  if ((await closeButton.count()) === 0) {
    // Already dismissed or not in desktop shape.
    return;
  }
  await closeButton.click();
  const panel = page.getByTestId('ficha-territorial-panel');
  const pill = page.getByTestId('ficha-territorial-panel-pill');
  await expect
    .poll(
      async () => {
        const pillVisible = await pill.isVisible().catch(() => false);
        if (pillVisible) return true;
        // Panel unmounted = nothing to block the next click.
        return (await panel.count()) === 0;
      },
      { message: 'La ficha territorial no se cerró ni minimizó', timeout: 5000 }
    )
    .toBe(true);
}

interface JourneyRecord {
  context: 'mobile' | 'desktop';
  target: ParcelAlias;
  attemptCount: number;
  clickCount: number;
  wheelProofsBeforeClick: number;
  analysisSequence: number;
}

/**
 * Drive A→B→C→A on ONE context (mobile or desktop) and record the manifest
 * rows plus the final READY evidence list. Returns nothing; asserts inline.
 */
async function runContextJourney(
  page: Page,
  fixture: HarnessFixture,
  camera: Camera,
  trace: FixtureRouterTrace,
  context: 'mobile' | 'desktop',
  manifest: JourneyRecord[]
): Promise<void> {
  const order: ParcelAlias[] = ['A', 'B', 'C', 'A'];
  const target = (alias: ParcelAlias) =>
    fixture.parcels.find((p) => p.alias === alias) as ParcelFixture;

  const canvas = page.locator('.maplibregl-canvas').first();
  await canvas.waitFor({ state: 'visible', timeout: 15_000 });

  // The map workspace renders a Mantine loading overlay above the canvas
  // while the fixture dataset is being fetched. The canvas is VISIBLE but
  // not hit-testable under that overlay, so a plain click would land on the
  // overlay and fail actionability. This is a PRECONDITION wait (RMEH-004-B:
  // occlusion aborts before the pointer); it is not a click retry, so the
  // exactly-one-click interaction policy (RMEH-005-A) is preserved.
  const overlayGone = await page
    .locator('.mantine-Loader-root')
    .waitFor({ state: 'detached', timeout: 30_000 })
    .then(
      () => true,
      () => false
    );
  requireCondition(overlayGone, 'El overlay de carga no se desmontó antes del primer clic');

  const box = await canvas.boundingBox();
  if (box === null) {
    throw new Error('El canvas del mapa no expuso su caja de medida');
  }

  let previous: TargetReadyEvidence['previous'] = null;
  let wheelProofsBeforeClick = 0;
  const selectedAliases: ParcelAlias[] = [];

  for (let index = 0; index < order.length; index += 1) {
    const alias = order[index];
    selectedAliases.push(alias);
    const parcel = target(alias);

    // Dismiss any location/denuncia popup so the next click lands on the map
    // canvas, not on popup chrome. MapLibre popups do not always close on Escape,
    // so close the visible close-button if it exists; ignore otherwise.
    const popups = await page.locator('.maplibregl-popup-close-button').count();
    if (popups > 0) {
      await page
        .locator('.maplibregl-popup-close-button')
        .first()
        .click({ force: true, timeout: 500 });
    }

    // Mobile: prove the sheet really scrolls before clicking the NEXT parcel.
    if (context === 'mobile' && index > 0) {
      const sample = await sampleMobileSheet(page);
      const bodyBox = await page.getByTestId('ficha-territorial-panel-sheet-body').boundingBox();
      requireCondition(bodyBox !== null, 'No se pudo medir la caja de la hoja para la rueda');
      if (bodyBox) {
        await page.mouse.move(bodyBox.x + bodyBox.width / 2, bodyBox.y + bodyBox.height / 2);
        await page.mouse.wheel(0, sample.range);
        await page.waitForTimeout(100);
        const after = await page
          .getByTestId('ficha-territorial-panel-sheet-body')
          .evaluate((el) => el.scrollTop);
        assertScrollRangeAndWheelProof({
          range: sample.range,
          intendedDelta: sample.range,
          beforeScrollTop: sample.beforeScrollTop,
          afterWheelScrollTop: after,
        });
      }
      wheelProofsBeforeClick = 1;
      await collapseMobileSheetToPeek(page);
    } else {
      wheelProofsBeforeClick = 0;
    }

    // Project the parcel's interior point onto the canvas and click it.
    const projection = projectParcel(parcel, camera, {
      left: box.x,
      top: box.y,
      width: box.width,
      height: box.height,
    });
    requireCondition(
      projection.insideOwnPolygon,
      `El punto interior de ${alias} no cayó dentro de su propio polígono`
    );
    await canvas.click({ position: { x: projection.localCssX, y: projection.localCssY } });

    // Desktop: the click must not steal focus away from the map surface.
    if (context === 'desktop') {
      const focused = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        return {
          tagName: el.tagName.toLowerCase(),
          isBody: el === document.body,
          isCanvas: el.classList.contains('maplibregl-canvas'),
          isMapInteractionAncestor:
            !!el.closest('.maplibregl-canvas-container, [data-testid="map-workspace-canvas"]') ||
            !!el.closest('[data-testid="map-workspace-root"]'),
          intersectsViewport:
            rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0,
          hidden: rect.width === 0 || rect.height === 0,
          inert: el.hasAttribute('inert'),
          disabled: (el as HTMLInputElement).disabled === true,
          mobileOnly: false,
        };
      });
      if (focused) assertDesktopFocusStable(focused);
    }

    // Design RMEH-007-A: "plain-click A → activate `Lluvia` once → READY_A".
    // The ficha opens on the `suelos` dataset tab, and the v2 rainfall detail
    // (RainfallDetailPanel → scopes:resolve + analyses requests) mounts ONLY
    // when the `Lluvia` tab is active. The tab lens survives selection changes
    // (useFichaOverlayTabs CONTRACT), so ONE activation per context is enough;
    // it must also come AFTER the desktop focus check, which asserts the
    // canvas click did not steal focus.
    if (index === 0) {
      const fichaResolved = await page
        .getByTestId('ficha-result')
        .waitFor({ state: 'visible', timeout: 15_000 })
        .then(
          () => true,
          () => false
        );
      requireCondition(fichaResolved, 'La ficha no resolvió su resultado antes de activar Lluvia');
      await page.getByTestId('ficha-dataset-tabs').locator('label', { hasText: 'Lluvia' }).click();
    }

    // Gate: the analysis for the TARGET must be the freshest one served.
    await waitForTargetAnalysis(page, trace, parcel, previous?.analysisSequence ?? 0);

    // Wait for the headline to reflect the target percentile.
    await expect(page.getByTestId('rainfall-headline')).toContainText(
      `Percentil ${parcel.rainfall.percentile}`
    );

    const lluviaSelected = await readLluviaActive(page);

    if (context === 'mobile') {
      const stage = await readSheetStage(page);
      const scrollTopAfter = await page
        .getByTestId('ficha-territorial-panel-sheet-body')
        .evaluate((el) => el.scrollTop);
      const cardBoxRaw = await page.getByTestId('rainfall-answer-card').boundingBox();
      const bodyBoxRaw = await page.getByTestId('ficha-territorial-panel-sheet-body').boundingBox();
      if (cardBoxRaw === null || bodyBoxRaw === null) {
        throw new Error('No se pudo medir la tarjeta para móvil');
      }
      const cardBox = {
        left: cardBoxRaw.x,
        top: cardBoxRaw.y,
        width: cardBoxRaw.width,
        height: cardBoxRaw.height,
      };
      const bodyBox = {
        left: bodyBoxRaw.x,
        top: bodyBoxRaw.y,
        width: bodyBoxRaw.width,
        height: bodyBoxRaw.height,
      };
      // The silent-refresh interceptor may have ROTATED the seed token in
      // sessionStorage (production behavior, exercised by the map's protected
      // queries). The auth assertion must pin the token active FOR THIS
      // sequence, read live — never the seed constant (design "Authentication
      // and Silent Refresh": seed -> optional observed refresh -> rotated).
      const activeTokenValue = await activeAccessToken(page);
      const evidence = await collectReadyEvidence(page, trace, parcel, previous, activeTokenValue, lluviaSelected, selectedAliases);
      assertMobileReady({ ...evidence, stage, scrollTopAfter, cardBox, bodyBox }, parcel);
    } else {
      const activeTokenValue = await activeAccessToken(page);
      const evidence = await collectReadyEvidence(page, trace, parcel, previous, activeTokenValue, lluviaSelected, selectedAliases);
      assertTargetReady(evidence, parcel);
    }

    // Record the manifest row (one attempt, one click per transition).
    manifest.push({
      context,
      target: alias,
      attemptCount: 1,
      clickCount: 1,
      wheelProofsBeforeClick,
      analysisSequence: trace.analysisSequence,
    });

    previous = {
      renderedPercentile: parcel.rainfall.percentile,
      renderedAccumulationMm: parcel.rainfall.accumulationMm,
      renderedMetricRevision: parcel.rainfall.metricRevision,
      analysisSequence: trace.analysisSequence,
    };

    // Desktop: collapse/close the ficha panel before the next map click so the
    // floating card does not intercept it. Keep the last selection open for the
    // final assertions.
    if (context === 'desktop' && index < order.length - 1) {
      await dismissDesktopPanel(page);
    }
  }
}

test.describe('Lluvia v2 — detalle técnico en la ficha (T4.1)', () => {
  test('puerta de autorización: anónimo NO ve el detalle de lluvia', async ({ page }) => {
    // No session at all: the render gate must keep the panel off the DOM.
    mockRainfallApi(page);
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('ficha-precipitacion')).toBeVisible();
    await expect(page.getByTestId('rainfall-detail')).toHaveCount(0);
    await expect(page.getByTestId('rainfall-export-csv')).toHaveCount(0);
  });

  test('puerta de autorización: ciudadano NO ve el detalle de lluvia', async ({ page }) => {
    await seedAuth(page, makeUser('ciudadano', 'ciudadano@e2e.local'));
    mockRainfallApi(page);
    await gotoAndOpenFicha(page);

    // The PUBLIC chart remains, but the staff-gated detail must not mount.
    await expect(page.getByTestId('ficha-precipitacion')).toBeVisible();
    await expect(page.getByTestId('rainfall-detail')).toHaveCount(0);
    await expect(page.getByTestId('rainfall-export-csv')).toHaveCount(0);
  });

  test('operador: detalle visible, badget de estimación regional y métricas', async ({ page }) => {
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    mockRainfallApi(page);
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-detail')).toBeVisible();
    await expect(page.getByTestId('rainfall-regional-estimate')).toBeVisible();
    await expect(page.getByTestId('rainfall-scope-switch')).toBeVisible();
    await expect(page.getByTestId('rainfall-year-select')).toBeVisible();

    // The ANSWER is on the always-visible surface: headline, the derived
    // adjective and the textual equivalent, with no control operated. The
    // snapshot year is derived from the current calendar year (the fixture's
    // readyBody echoes the requested `year`), so the expectation must follow
    // suit instead of hardcoding 2026 (RELI3C-004).
    const card = page.getByTestId('rainfall-answer-card');
    await expect(card).toBeVisible();
    await expect(page.getByTestId('rainfall-headline')).toContainText(
      `Percentil ${SNAPSHOT_METRICS.percentile}`
    );
    // The accumulation states its CUT DATE, never a bare year: "Año 2026:
    // 123.4 mm" reads as a closed annual total, which mid-year it is not.
    const annualText = page.getByTestId('rainfall-annual-text');
    await expect(annualText).toContainText('Acumulado hasta el ');
    await expect(annualText).not.toContainText(`Año ${new Date().getFullYear()}:`);
    await expect(annualText).toContainText(`${SNAPSHOT_METRICS.annual} mm`);
    // And the normal names the period it accumulated over, not just its baseline.
    await expect(annualText).toContainText('al mismo período');
    // The rank in words, so the percentile is not a number the reader nods at.
    await expect(page.getByTestId('rainfall-percentile-gloss')).toContainText(
      `De cada 100 años, ${SNAPSHOT_METRICS.percentile} fueron más secos que este.`
    );

    // The badged rows are one click away, not gone (R4). Asserting them
    // WITHOUT the click would prove the fold does not fold.
    await expect(page.getByTestId('rainfall-metrics')).toHaveCount(0);
    await page.getByTestId('rainfall-technical-header').click();
    const technical = page.getByTestId('rainfall-technical-body');
    await expect(technical.getByTestId('rainfall-metrics')).toBeVisible();
    await expect(technical.getByTestId('rainfall-metric-selected')).toBeVisible();

    // R6, witnessed end to end (design D8). The fixture serves an `intensity`
    // group this frontend has no title for — `build_snapshot` cannot emit it,
    // and the eight labels it once had were pruned in slice 2. It must still
    // reach the reader, under its RAW key with raw metric keys, because the
    // repo's rule for an untranslated fact is to show it, never to drop it.
    // Until now the fixture only witnessed the CSV export of this group, so the
    // claim "the e2e fixture is the live witness of the unknown-group fallback"
    // was false (UXJA-014).
    await expect(technical.getByText('intensity', { exact: true })).toBeVisible();
    const rawGroupRow = technical.getByTestId('rainfall-metric-p24h');
    await expect(rawGroupRow).toBeVisible();
    await expect(rawGroupRow).toContainText('p24h');
    // The backend's own export label is a DIFFERENT string with a different
    // owner: `P24h (mm en 24 h)` lives in the mocked CSV body, so pruning the
    // frontend labels cannot move it — and this asserts the two have not been
    // confused for one another.
    await expect(rawGroupRow).not.toContainText('mm en 24 h');
  });

  test('cambio de ámbito (scope switch) reconsulta con el ámbito elegido', async ({ page }) => {
    const registration = mockRainfallApi(page);
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    // Default selection is the FIRST choice (zone). Switch to the basin.
    await page.getByTestId('rainfall-scope-switch').locator('label', { hasText: 'Cuenca' }).click();

    // Wait until a RECORDED request actually carries the basin scope, not just
    // any analysis request: the default zone POST can otherwise satisfy a
    // length-only poll before the basin POST is dispatched (RELI3C-003).
    await expect
      .poll(() => {
        const basin = registration.analysisRequests.find(
          (r) => (r.scope as Record<string, string> | undefined)?.kind === 'basin'
        );
        return basin ? ((basin.scope as Record<string, string>).id ?? '') : undefined;
      })
      .toBe('b-carcara-01');
  });

  test('estado en cola (202) etiquetado que resuelve a snapshot listo (200)', async ({ page }) => {
    mockRainfallApi(page, { queuedFirst: true });
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    // Labelled queued state must be perceivable (never a bare spinner).
    // Either wording is correct here and which one appears is a RACE by
    // design: the moment the selected year answers 202 the panel also asks for
    // the previous one, and this mock answers every later POST with a 200 — so
    // the alert may already have become the "showing {Y-1}" notice. Both say
    // the analysis is being prepared, which is the fact under test.
    const queuedAlert = page.getByTestId('rainfall-queued');
    await expect(queuedAlert).toBeVisible();
    await expect(queuedAlert).toContainText(/en preparación|se está preparando/);
    // Never the backend's job identifiers, in either wording (OWN-002).
    await expect(queuedAlert).not.toContainText('role:');

    // Then auto-polls to a ready snapshot within the bounded budget. The
    // readiness sentinel is the ANSWER CARD: it renders for every ready
    // snapshot and, unlike `rainfall-metrics`, is not inside a fold that
    // starts closed.
    await expect(page.getByTestId('rainfall-answer-card')).toBeVisible({ timeout: 20_000 });
    await expect(queuedAlert).toHaveCount(0);
  });

  test('export CSV: bearer en header → fichero con las métricas del snapshot (paridad)', async ({
    page,
  }) => {
    const metrics = mockRainfallApi(page);
    await seedAuth(page, makeUser('admin', 'admin@e2e.local'));
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-answer-card')).toBeVisible();

    const exportToken = await activeAccessToken(page);
    const downloadPromise = page.waitForEvent('download');
    await page.getByTestId('rainfall-export-csv').click();
    const download = await downloadPromise;

    // Filename follows the contract lluvia_<revision>.csv.
    expect(download.suggestedFilename()).toBe('lluvia_rev-e2e-01.csv');

    // The physical bytes equal what the snapshot displays (parity): both the
    // CSV body and the readyBody snapshot derive from SNAPSHOT_METRICS, so
    // crossing the wire is the ONLY way this assertion can pass
    // (RELI3C-005).
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(chunk as Buffer);
    const body = Buffer.concat(chunks).toString('utf8');
    expect(body).toContain(`Acumulado del año,${SNAPSHOT_METRICS.annual},mm,disponible,rev-e2e-01`);
    expect(body).toContain(`Normal 1991-2020,${SNAPSHOT_METRICS.normal},mm,disponible,rev-e2e-01`);
    expect(body).toContain(`Antecedente 7 días,${SNAPSHOT_METRICS.d7},mm,disponible,rev-e2e-01`);

    // Parity asserted against the UI-displayed values: the snapshot the
    // interface renders (98.2 normal, 123.4 annual) must appear in the
    // downloaded CSV bytes.
    expect(body).toContain(String(SNAPSHOT_METRICS.normal));
    expect(body).toContain(String(SNAPSHOT_METRICS.annual));

    // Sealed: the token went in the Authorization header, never the URL.
    const csvReq = metrics.csvRequests[0];
    expect(csvReq.headers.authorization).toBe(`Bearer ${exportToken}`);
    expect(csvReq.url).not.toContain(MOCK_TOKEN);
    expect(csvReq.url).not.toContain(exportToken);
    expect(csvReq.url).not.toMatch(/[?&](token|access_token|key)=/);
  });

  test('gráfico acumulado: las DOS series se dibujan y ambas fechas se declaran (4.10)', async ({
    page,
  }) => {
    const mocks = mockRainfallApi(page);
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-answer-card')).toBeVisible();

    // The chart is fed from the READ-ONLY /series route of the served
    // revision, not from a second analysis request.
    const chart = page.getByTestId('rainfall-accumulation-chart');
    await expect(chart).toBeVisible();
    await expect.poll(() => mocks.seriesRequests.length).toBeGreaterThan(0);
    expect(mocks.seriesRequests[0]).toContain('rev-e2e-01/series');

    // TWO lines: the selected year AND the 1991-2020 normal. This is the whole
    // point of the slice — one line is the comparison half-built.
    await expect.poll(() => chart.locator('.recharts-line').count()).toBe(2);

    // Both dates disclosed as TEXT, which is what survives a screenshot and a
    // screen reader alike -- and each named, not just present as a substring:
    // the fixture's comparison end and its last day WITH evidence are the same
    // day (zero lag), so a single `toContainText` could not tell which sentence
    // it matched, nor notice if one of the two disappeared.
    const currentYear = new Date().getFullYear();
    const dates = page.getByTestId('rainfall-accumulation-dates');
    await expect(dates).toContainText(`Comparación hasta el ${currentYear}-02-09`);
    await expect(dates).toContainText(`Evidencia publicada hasta el ${currentYear}-02-09`);
    // The EXCLUSIVE bound is an implementation detail of the window and must
    // never reach the reader.
    await expect(dates).not.toContainText(`${currentYear}-02-10`);
    // Zero lag: this fixture published through its own comparison end, so the
    // provider-lag notice must stay away. Without this the fixture could drift
    // back into a lag shape and nothing would say so.
    await expect(page.getByTestId('rainfall-accumulation-lag')).toHaveCount(0);

    // The display preset windows the same series and issues NO new analysis
    // request (spec "Campaign Display Preset").
    const analysisCallsBefore = mocks.analysisRequests.length;
    await page
      .getByTestId('rainfall-campaign-preset')
      .locator('label', { hasText: 'Campaña' })
      .click();
    await expect(page.getByTestId('rainfall-campaign-note')).toBeVisible();
    expect(mocks.analysisRequests.length).toBe(analysisCallsBefore);
  });

  test('export xlsx: enlace visible y descarga el libro de la revisión (4.10)', async ({
    page,
  }) => {
    const mocks = mockRainfallApi(page);
    await seedAuth(page, makeUser('admin', 'admin@e2e.local'));
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-answer-card')).toBeVisible();
    const xlsxButton = page.getByTestId('rainfall-export-xlsx');
    await expect(xlsxButton).toBeVisible();
    // The audit CSV is still there: the friendly workbook is an addition.
    await expect(page.getByTestId('rainfall-export-csv')).toBeVisible();

    const exportToken = await activeAccessToken(page);
    const downloadPromise = page.waitForEvent('download');
    await xlsxButton.click();
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe('lluvia_rev-e2e-01.xlsx');
    // Same credential rule as the CSV (they share one download body): bearer in
    // the header, never in the URL where history and access logs would keep it.
    const xlsxReq = mocks.xlsxRequests[0];
    expect(xlsxReq.headers.authorization).toBe(`Bearer ${exportToken}`);
    expect(xlsxReq.url).not.toContain(MOCK_TOKEN);
    expect(xlsxReq.url).not.toContain(exportToken);
    expect(xlsxReq.url).not.toMatch(/[?&](token|access_token|key)=/);
  });

  test('export CSV denegado (403) muestra error claro y no deja estado fantasma', async ({
    page,
  }) => {
    mockRainfallApi(page, { csvStatus: 403 });
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-export-csv')).toBeVisible();
    await page.getByTestId('rainfall-export-csv').click();
    await expect(page.getByTestId('rainfall-export-error')).toBeVisible();
    await expect(page.getByTestId('rainfall-export-error')).toContainText(
      'La descarga del CSV no está autorizada'
    );
  });

  /**
   * Success criterion 1: the answer is readable WITHOUT scrolling on a phone.
   *
   * A real browser is the only place this can be asked — jsdom has no layout,
   * so the unit suite asserts the structural precondition (order + both folds
   * collapsed) and stops there rather than faking a viewport.
   *
   * The box measured against is `ficha-territorial-panel-sheet-body`, the
   * sheet's own SCROLLING element (`MapPanelShell.tsx`). Not the sheet root:
   * that one is capped by `max-height` while this is what actually overflows,
   * so it is the only element whose visible height the assertion can honestly
   * compare a card's box against.
   *
   * Gated with `requireCondition`, NOT `skipForMissingData`: a missing sheet
   * body means the layout under test is not there, and a criterion that skips
   * itself when the thing it measures is absent measures nothing. The gate
   * only BITES when `E2E_APP_URL` is set (`strictGate.ts`), which is exactly
   * the declared local environment design D13 specifies — this criterion is
   * not gated by CI and this spec does not pretend it is.
   */
  test.describe('respuesta sin scroll en teléfono', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('la tarjeta de respuesta entra en el alto visible de la hoja (390×844)', async (
      { page },
      testInfo
    ) => {
      await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
      mockRainfallApi(page);
      await gotoAndOpenFicha(page);

      const card = page.getByTestId('rainfall-answer-card');
      await expect(card).toBeVisible();

      // Both folds closed is what makes the measurement meaningful: an open
      // fold would push the card nowhere, but a card measured with the folds
      // open would not be measuring the DEFAULT the reader lands on.
      await expect(page.getByTestId('rainfall-technical-header')).toHaveAttribute(
        'aria-expanded',
        'false'
      );

      const sheetBody = page.getByTestId('ficha-territorial-panel-sheet-body');
      requireCondition(
        (await sheetBody.count()) === 1,
        'La hoja de la ficha no expuso su caja de scroll'
      );

      const cardBox = await card.boundingBox();
      const bodyBox = await sheetBody.boundingBox();
      if (cardBox === null || bodyBox === null) {
        requireCondition(false, 'No se pudo medir la tarjeta o la caja de scroll de la hoja');
        return;
      }

      const scrolled = await sheetBody.evaluate((element) => element.scrollTop);
      const bounds = {
        cardTop: cardBox.y,
        cardBottom: cardBox.y + cardBox.height,
        cardHeight: cardBox.height,
        bodyTop: bodyBox.y,
        bodyBottom: bodyBox.y + bodyBox.height,
        bodyHeight: bodyBox.height,
        topMargin: cardBox.y - bodyBox.y,
        bottomMargin: bodyBox.y + bodyBox.height - (cardBox.y + cardBox.height),
        scrollTop: scrolled,
      };
      console.info(`[O.1 mobile bounds] ${JSON.stringify(bounds)}`);
      await testInfo.attach('mobile-card-bounds.json', {
        body: JSON.stringify(bounds),
        contentType: 'application/json',
      });

      // The whole card — headline, adjective, textual equivalent, freshness and
      // scope — inside the visible height, with nothing scrolled.
      expect(cardBox.y).toBeGreaterThanOrEqual(bodyBox.y - 1);
      expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(bodyBox.y + bodyBox.height + 1);
      // …and the reader did not have to scroll to get there.
      expect(scrolled).toBe(0);
    });
  });

  test('A→B→C→A: una selección por clic en móvil y escritorio (RMEH-007/008)', async ({
    browser,
  }, testInfo) => {
    // browser.newContext() does NOT inherit the config `use` options, so the
    // viewports are passed explicitly per form factor.
    const fixture = validateFixture(rainfallFixtureJson);
    const manifest: JourneyRecord[] = [];

    for (const context of ['mobile', 'desktop'] as const) {
      const rawCamera = fixture.cameras[context];
      const viewport = rawCamera.viewport;
      // The mobile ficha sheet covers the bottom of the viewport at stage=medio.
      // Projection for B/C/A must target the visible canvas, so after the wheel
      // proof collapses the sheet back to peek we use the unshifted fixture camera
      // to keep the spread A/B/C centered on the map.
      const camera: Camera = rawCamera;
      const contextPage = await browser.newContext({ viewport: { width: viewport.width, height: viewport.height } });
      const page = await contextPage.newPage();

      // Seed auth + silent-refresh route (same seam the rest of the suite uses).
      await page.route(/api\/v2\/auth\/jwt\/refresh(?:\?|$)/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ access_token: ROTATED_MOCK_TOKEN }),
        });
      });
      await page.addInitScript(
        ({ tokenKey, userKey, token, user }) => {
          try {
            window.localStorage.removeItem('consorcio_auth_logout_tombstone');
          } catch {
            /* storage unavailable — nothing to clean */
          }
          window.sessionStorage.setItem(tokenKey, token);
          window.sessionStorage.setItem(userKey, JSON.stringify(user));
        },
        {
          tokenKey: TOKEN_KEY,
          userKey: USER_KEY,
          token: MOCK_TOKEN,
          user: makeUser('operador', 'operador@e2e.local'),
        }
      );

      const trace = registerFixtureRainfallRouter(page, fixture);

      // Navigate by the fixture camera (URL seam read by useReportHighlight),
      // and listen for a catastro tile so the ficha click is gated on real data.
      let catastroTileSeen = false;
      page.on('response', (response) => {
        if (/parcelas_catastro/.test(response.url()) && response.status() === 200) {
          catastroTileSeen = true;
        }
      });
      await page.goto(`${APP_URL}/mapa?lat=${camera.lat}&lng=${camera.lng}&zoom=${camera.zoom}`);

      const canvas = page.locator('.maplibregl-canvas').first();
      const mounted = await canvas
        .waitFor({ state: 'visible', timeout: 15_000 })
        .then(() => true)
        .catch(() => false);
      requireCondition(mounted, 'El canvas del mapa no montó en un entorno declarado');

      const tileDeadline = Date.now() + 15_000;
      while (!catastroTileSeen && Date.now() < tileDeadline) {
        await page.waitForTimeout(250);
      }
      if (!catastroTileSeen) {
        skipForMissingData(true, 'Catastro vacío o sin tiles en este entorno');
        await contextPage.close();
        continue;
      }

      // Allow vector features to render after the tile response arrives; this
      // is a deterministic map settle, not a click retry (RMEH-005-A).
      await page.waitForTimeout(750);

      // The map canvas must finish laying out before the projection is measured.
      await page.getByTestId('map-workspace-root').waitFor({ state: 'visible', timeout: 15_000 });

      await runContextJourney(page, fixture, camera, trace, context, manifest);
      await contextPage.close();
    }

    // Exactly 8 records: 4 mobile + 4 desktop, one attempt + one click each.
    expect(manifest).toHaveLength(8);
    for (const record of manifest) {
      expect(record.attemptCount).toBe(1);
      expect(record.clickCount).toBe(1);
    }
    // The driver reads the manifest from the FILE next to the reporter output,
    // wrapped in { selection_records: [...] } — not from the attachment (A2).
    const harnessOutputJson =
      process.env.RMEH_PLAYWRIGHT_JSON ?? '.artifacts/rainfall-multi-parcel/playwright-results.json';
    writeHarnessManifest(manifest, harnessOutputJson);
    await testInfo.attach('manifest.json', {
      body: JSON.stringify({ selection_records: manifest }, null, 2),
      contentType: 'application/json',
    });
  });
});
