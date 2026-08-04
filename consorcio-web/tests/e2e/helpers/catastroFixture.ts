/**
 * catastroFixture.ts — a DETERMINISTIC way to open the ficha territorial.
 *
 * WHY THIS EXISTS
 * `ficha-territorial.spec.ts` opens the ficha by clicking the canvas centre and
 * then skipping when "the click didn't land on a parcel". That is the reason
 * `mapa-viewport-movil.spec.ts` left its minimize-pill test as `fixme`: a test
 * whose precondition is a coin flip is either flaky or green-empty.
 *
 * THE THREE OPTIONS THAT WERE ON THE TABLE (B4c/T2)
 *
 *   (a) Click a KNOWN point of the map.  ← CHOSEN
 *       `/mapa` already accepts `?lat=&lng=&zoom=` (`useReportHighlight`,
 *       shipped for the admin "Ver en mapa" button): it `flyTo`s those exact
 *       coordinates, so the parcel we pick ends up under the CANVAS CENTRE and
 *       no projection math is needed on the test side. Nothing in production
 *       changes, the entry point is a real user-facing feature, and the only
 *       inputs are a lng/lat pair plus a pixel offset.
 *
 *   (b) A URL/state that opens the ficha directly.
 *       Does not exist. `/mapa` has no `validateSearch` and the ficha selection
 *       lives entirely inside `useFichaInteraction` (React state, not the URL).
 *       Building one would mean shipping a deep-link feature nobody asked for,
 *       to be exercised only by a test — the classic "test-shaped production
 *       code" trade we don't want.
 *
 *   (c) A test-only `postMessage` / event hook.
 *       Would put a click-simulation backdoor into the production bundle (or
 *       behind an `import.meta.env` branch, i.e. shipping code paths that only
 *       exist for CI). It also tests the backdoor, not the map: the whole point
 *       of this e2e is that a real click on a real parcel resolves.
 *
 * THE COORDINATE (source + why it is stable)
 * Derived by `tests/e2e/helpers/derive-catastro-fixture.mjs` (run it to
 * reproduce every number below) from the repo's own bundled dataset,
 * `consorcio-web/public/data/catastro_rural_cu.geojson` (IDECor catastro rural,
 * the same `parcelas_catastro` set the map's Martin tiles serve): parcel
 * `Nomenclatura = 3603003210041000` (desig. `321-0410`, dpto. Unión, 2 387 ha)
 * — the largest single-ring parcel in the file. Measured by that script over
 * 1 322 features:
 *   - its centroid lies INSIDE the polygon,
 *   - the nearest edge is 1 649 m away,
 *   - exactly ONE feature in the file contains that point (no overlap).
 * At `zoom=16` (2.02 m/px at this latitude) the 60 px click offset used below
 * is 121 m from the centre — an order of magnitude inside the parcel. A
 * cadastral re-survey would have to redraw a 2 400 ha lot for this to miss.
 *
 * THE OFFSET
 * `useReportHighlight` also drops a `maplibregl.Marker` + auto-opened popup at
 * the very coordinates it flies to, so the canvas CENTRE is covered by the
 * marker's DOM. The click is offset down-right, away from the popup (which is
 * anchored 24 px ABOVE the marker).
 *
 * NO FIXED SLEEPS (B4c fix round, REL-002)
 * The first version waited 3 s for "the camera settled and the tiles landed",
 * which is a timing assumption written by hand: too short on a cold edge, wasted
 * time otherwise, and silent either way. Settling is now OBSERVED:
 *   1. the SPA goes idle (`networkidle`), then
 *   2. a `parcelas_catastro` tile actually came back `200` — proof that Martin
 *      is serving parcels for the flown-to viewport, and implicitly that the
 *      camera got there;
 *   3. the click is retried inside a bounded poll until the panel opens, which
 *      absorbs the render frame after the tile arrives without pretending to
 *      know how long it takes. Re-clicking the same parcel is idempotent (a
 *      plain click is a fresh single selection).
 *
 * WHAT IS A SOFT GATE, AND WHY THE TILE CHECK IS THE REAL ONE (REL-003)
 * `probeFichaAvailability` probes `E2E_API_BASE` — the backend the TEST can
 * reach, which is NOT necessarily the backend the deployed bundle talks to (the
 * SPA uses its own `VITE_API_URL`, and the canary runs with no API base at all,
 * so the probe there is `unknown` by construction). A green probe therefore does
 * not prove the page's own backend or tile server is up. The real net is step 2:
 * no catastro tile ⇒ the caller skips with "tiles de catastro no disponibles"
 * instead of failing. Tiles present and the panel still closed IS a regression
 * and must fail.
 */

import { type APIRequestContext, type Page, request } from '@playwright/test';

import { APP_URL } from './mapWorkspace';

/** Interior point of parcel `3603003210041000` — see the module docstring. */
export const PARCELA_FIXTURE = {
  nomenclatura: '3603003210041000',
  lng: -62.446176,
  lat: -32.471267,
  /** High enough for the Martin `parcelas_catastro` source (minzoom 8). */
  zoom: 16,
} as const;

/** Click offset from the canvas centre, in CSS px — clears the marker + popup. */
const CLICK_OFFSET_PX = 60;

/** Martin layer name of the catastro source (`syncCatastroLayers`). */
const CATASTRO_TILE_PATTERN = /parcelas_catastro/;

/** Budgets for the two condition waits. Neither is a settle time. */
const TILE_TIMEOUT_MS = 20_000;
const CLICK_POLL_TIMEOUT_MS = 20_000;
const CLICK_POLL_INTERVAL_MS = 1_000;

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

export type FichaAvailability = 'on' | 'off' | 'unknown';

/**
 * Probe the ficha endpoint (same contract as `ficha-territorial.spec.ts`).
 * `off` = flag off or empty catastro, `unknown` = no backend reachable.
 *
 * Remember the probe/bundle split above: this is a cheap early skip, not the
 * real gate.
 */
export async function probeFichaAvailability(): Promise<FichaAvailability> {
  let ctx: APIRequestContext | null = null;
  try {
    ctx = await request.newContext({ baseURL: API_BASE });
    const res = await ctx.post('/api/v2/geo/analisis-zona', {
      data: { tipo: 'parcela', nomenclatura: '__probe__' },
    });
    if (res.status() === 503) {
      const body = (await res.json().catch(() => ({}))) as { codigo?: string };
      if (body.codigo === 'funcionalidad_no_disponible' || body.codigo === 'dataset_no_cargado') {
        return 'off';
      }
    }
    // 404 / 422 / 429 all prove the endpoint is live.
    return 'on';
  } catch {
    return 'unknown';
  } finally {
    await ctx?.dispose();
  }
}

export interface FixtureParcelaResult {
  /**
   * The workspace shell + WebGL canvas came up. STRUCTURAL — gate it with
   * `requireCondition` (fails in a declared environment).
   */
  readonly ready: boolean;
  /**
   * At least one `parcelas_catastro` tile came back `200` for the flown-to
   * viewport. ENVIRONMENTAL — gate it with `skipForMissingData`.
   */
  readonly catastroTilesAvailable: boolean;
  /** The ficha panel became visible after clicking the fixture parcel. */
  readonly fichaOpened: boolean;
}

/**
 * Navigate to `/mapa` centred on the fixture parcel, wait for its tiles and
 * click it.
 *
 * Never throws and never asserts: it reports what happened and the caller
 * decides which gate each fact belongs to (see {@link FixtureParcelaResult}).
 */
export async function clickFixtureParcela(page: Page): Promise<FixtureParcelaResult> {
  const { lat, lng, zoom } = PARCELA_FIXTURE;
  const notReady: FixtureParcelaResult = {
    ready: false,
    catastroTilesAvailable: false,
    fichaOpened: false,
  };

  // Subscribe BEFORE navigating: the tiles for the flown-to viewport are
  // requested while the camera is still moving.
  let catastroTileSeen = false;
  page.on('response', (response) => {
    if (!CATASTRO_TILE_PATTERN.test(response.url())) return;
    // 200 only: Martin answers 204 for a tile with no features, which proves
    // nothing about parcels being served here.
    if (response.status() === 200) catastroTileSeen = true;
  });

  try {
    await page.goto(`${APP_URL}/mapa?lat=${lat}&lng=${lng}&zoom=${zoom}`);
    await page.getByTestId('map-workspace-root').waitFor({ state: 'visible', timeout: 30_000 });
  } catch {
    return notReady;
  }

  const canvas = page.locator('.maplibregl-canvas').first();
  const mounted = await canvas
    .waitFor({ state: 'visible', timeout: 15_000 })
    .then(() => true)
    .catch(() => false);
  if (!mounted) return notReady;

  const box = await canvas.boundingBox();
  if (!box) return notReady;

  // (1) the SPA stops fetching, (2) a catastro tile actually arrived. Both are
  // conditions, neither is a clock. `networkidle` is best-effort: a page that
  // keeps polling something would otherwise time out here and we would lose the
  // more informative tile signal below.
  await page.waitForLoadState('networkidle', { timeout: TILE_TIMEOUT_MS }).catch(() => {});
  const tileDeadline = Date.now() + TILE_TIMEOUT_MS;
  while (!catastroTileSeen && Date.now() < tileDeadline) {
    await page.waitForTimeout(250);
  }
  if (!catastroTileSeen) {
    return { ready: true, catastroTilesAvailable: false, fichaOpened: false };
  }

  const position = {
    x: box.width / 2 + CLICK_OFFSET_PX,
    y: box.height / 2 + CLICK_OFFSET_PX,
  };
  const panel = page.getByTestId('ficha-territorial-panel');

  // Bounded retry instead of a guessed settle time: the only thing between an
  // arrived tile and a clickable feature is a render frame, and polling says so
  // honestly instead of hard-coding a number.
  const clickDeadline = Date.now() + CLICK_POLL_TIMEOUT_MS;
  let fichaOpened = false;
  while (!fichaOpened && Date.now() < clickDeadline) {
    await canvas.click({ position });
    fichaOpened = await panel
      .waitFor({ state: 'visible', timeout: CLICK_POLL_INTERVAL_MS })
      .then(() => true)
      .catch(() => false);
  }

  return { ready: true, catastroTilesAvailable: true, fichaOpened };
}
