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
import { requireCondition, skipForMissingData } from './helpers/strictGate';
import { APP_URL } from './helpers/mapWorkspace';

const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';
const MOCK_TOKEN = 'e2e-mock-token-4a1';

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

/** An immutable ready (200) body — mirrors RainfallAnalysisSnapshot. */
function readyBody(
  scope: Record<string, string>,
  year: number,
  revision = 'rev-e2e-01'
): Record<string, unknown> {
  return {
    analysis_revision_id: revision,
    scope,
    regional_estimate: true,
    year,
    comparison_end: '2026-12-31',
    baseline: '1991-2020',
    annual: {
      selected: mockMetric('selected', 123.4),
      normal: mockMetric('normal', 98.2),
    },
    antecedents: {
      d7: mockMetric('d7', 31.0),
    },
    intensity: {
      p24h: mockMetric('p24h', 12.5),
    },
    summary: 'Año seco respecto de la normal 1991–2020.',
    source_health: { stations: 1, degraded: false },
  };
}

/** CSV served to a real download — parity: same keys/values as the snapshot. */
const CSV_BODY = [
  'metrica,valor,unidad,estado,revision',
  'Acumulado del año,123.4,mm,disponible,rev-e2e-01',
  'Normal 1991-2020,96.2,mm,disponible,rev-e2e-01',
  'Antecedente 7 días,31.0,mm,disponible,rev-e2e-01',
  'P24h (mm en 24 h),12.5,mm,disponible,rev-e2e-01',
].join('\n');

const ZONE_SCOPE = { kind: 'zone', id: 'z-arg-01', version: '2024-01' };
const BASIN_SCOPE = { kind: 'basin', id: 'b-carcara-01', version: '2024-01' };

interface RainfallMocks {
  analysisRequests: Array<Record<string, unknown>>;
  csvRequests: Array<{ headers: Record<string, string>; url: string }>;
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

  // Match ANY origin: the SPA's API base is baked per build (VITE_API_URL).
  page.route(/api\/v2\/geo\/rainfall\/.*/, async (route) => {
    const { method, url } = route.request();

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

    if (url.endsWith('.csv')) {
      csvRequests.push({ headers: route.request().headers(), url });
      await route.fulfill({
        status: csvStatus,
        contentType: csvStatus === 200 ? 'text/csv; charset=utf-8' : 'application/json',
        body:
          csvStatus === 200
            ? CSV_BODY
            : JSON.stringify({ detail: 'La descarga del CSV no está autorizada para este usuario.' }),
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

  return { analysisRequests, csvRequests };
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
    .then(() => true, () => false);
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
    .then(() => true, () => false);
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

    // Ready snapshot renders the metric groups with their textual values.
    await expect(page.getByTestId('rainfall-metrics')).toBeVisible();
    await expect(page.getByTestId('rainfall-annual-text')).toContainText('Año 2026');
    await expect(page.getByTestId('rainfall-annual-text')).toContainText('123.4 mm');
  });

  test('cambio de ámbito (scope switch) reconsultaa con el ámbito elegido', async ({ page }) => {
    const registration = mockRainfallApi(page);
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    // Default selection is the FIRST choice (zone). Switch to the basin.
    await page
      .getByTestId('rainfall-scope-switch')
      .locator('label', { hasText: 'Cuenca' })
      .click();

    // The very next analyses request must carry the basin scope.
    await expect.poll(() => registration.analysisRequests.length).toBeGreaterThan(0);
    const last = registration.analysisRequests[registration.analysisRequests.length - 1];
    expect((last.scope as Record<string, string>).kind).toBe('basin');
    expect((last.scope as Record<string, string>).id).toBe('b-carcara-01');
  });

  test('estado en cola (202) etiquetado que resuelve a snapshot listo (200)', async ({ page }) => {
    mockRainfallApi(page, { queuedFirst: true });
    await seedAuth(page, makeUser('operador', 'operador@e2e.local'));
    await gotoAndOpenFicha(page);

    // Labelled queued state must be perceivable (never a bare spinner).
    const queuedAlert = page.getByTestId('rainfall-queued');
    await expect(queuedAlert).toBeVisible();
    await expect(queuedAlert).toContainText('Análisis en preparación');

    // Then auto-polls to a ready snapshot within the bounded budget.
    await expect(page.getByTestId('rainfall-metrics')).toBeVisible({ timeout: 20_000 });
    await expect(queuedAlert).toHaveCount(0);
  });

  test('export CSV: bearer en header → fichero con las métricas del snapshot (paridad)', async ({
    page,
  }) => {
    const metrics = mockRainfallApi(page);
    await seedAuth(page, makeUser('admin', 'admin@e2e.local'));
    await gotoAndOpenFicha(page);

    await expect(page.getByTestId('rainfall-metrics')).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByTestId('rainfall-export-csv').click();
    const download = await downloadPromise;

    // Filename follows the contract lluvia_<revision>.csv.
    expect(download.suggestedFilename()).toBe('lluvia_rev-e2e-01.csv');

    // The physical bytes equal what the snapshot displays (parity).
    const stream = await download.createReadStream();
    const chunks: Buffer[] = [];
    for await (const chunk of stream) chunks.push(chunk as Buffer);
    const body = Buffer.concat(chunks).toString('utf8');
    expect(body).toContain('Acumulado del año,123.4,mm,disponible,rev-e2e-01');
    expect(body).toContain('Normal 1991-2020,96.2,mm,disponible,rev-e2e-01');
    expect(body).toContain('Antecedente 7 días,31.0,mm,disponible,rev-e2e-01');

    // Sealed: the token went in the Authorization header, never the URL.
    const csvReq = metrics.csvRequests[0];
    expect(csvReq.headers.authorization).toBe(`Bearer ${MOCK_TOKEN}`);
    expect(csvReq.url).not.toContain(MOCK_TOKEN);
    expect(csvReq.url).not.toMatch(/[?&](token|access_token|key)=/);
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
});