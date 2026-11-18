/**
 * informe-area.spec.ts — informe de área PR 1, T4 (S6).
 *
 * The plan's acceptance scenario: pick two subcuencas from the ficha panel's
 * "Informe de área" flow and read the per-subcuenca breakdown, plus the
 * `modo=trabajo` notice, keyboard operability and the 60-subcuenca preview
 * render budget (p95 < 1,5 s measured against a mocked network — see the
 * p95 test for what that number does and does not measure).
 *
 * ⚠️ WHY A NEW FILE (not extending ficha-territorial.spec.ts): that spec is a
 * LIVE-PROBE suite — it POSTs the real API first and skips when the ficha flag
 * is off. This suite is the opposite contract (tramo-survey.spec.ts pattern):
 * every read is stubbed at the network level, so it MUST run green with no
 * backend at all and never depends on `ficha_enabled`. Mixing the two contracts
 * in one file would make the canary (`test:e2e:canary`, which explicitly lists
 * ficha-territorial.spec.ts and runs against production) execute mocked tests
 * against an unmocked deploy. It also keeps the new feature out of the prod
 * canary until the PR merges.
 *
 * Entry path (deterministic, no tile data): seed an operator session → the
 * real Herramientas menu → "Dibujar polígono" → trace a polygon on the canvas
 * (MapboxDraw needs no data) → the `tipo=poligono` ficha panel opens → its
 * "Informe de área" button opens the drawer. Selection happens through the
 * Lista tab (checkboxes) because map-click selection depends on where the
 * camera looks — the list is the deterministic path (reported choice).
 */

import { expect, type Page, test } from '@playwright/test';

import { APP_URL } from './helpers/mapWorkspace';
import { requireCondition } from './helpers/strictGate';

// ── catalog (/geo/basins fixture) ─────────────────────────────────────────────

const CUENCA_TERCERO = 'Tercero — Arroyos';
const CUENCA_CHOCAN = 'Chocancharava';
const CUENCA_PINTO = 'Pinto';

interface ZonaFixture {
  readonly id: string;
  readonly nombre: string;
  readonly cuenca: string;
  readonly ha: number;
}

/** Two small zonas for the happy path, two big ones for `modo=trabajo`, 60 for the p95. */
const ZONAS: readonly ZonaFixture[] = [
  { id: 'z-tercero-algodon', nombre: 'Arroyo Algodón', cuenca: CUENCA_TERCERO, ha: 900.5 },
  { id: 'z-tercero-litin', nombre: 'Arroyo Litín', cuenca: CUENCA_TERCERO, ha: 900.5 },
  { id: 'z-chocan-mojarras', nombre: 'Arroyo Las Mojarras', cuenca: CUENCA_CHOCAN, ha: 21000.6 },
  { id: 'z-chocan-desviador', nombre: 'Canal Desviador', cuenca: CUENCA_CHOCAN, ha: 20229.4 },
  ...Array.from({ length: 60 }, (_, i) => {
    const numero = String(i + 1).padStart(2, '0');
    return {
      id: `z-pinto-${numero}`,
      nombre: `Subcuenca Pinto ${numero}`,
      cuenca: CUENCA_PINTO,
      // 60 × 500 = 30 000 ha: under the 35 000 ha online cap, so the p95 path
      // measures the ONLINE preview render, not the cap-alert branch.
      ha: 500.0,
    } satisfies ZonaFixture;
  }),
];

const ZONA_POR_ID = new Map(ZONAS.map((zona) => [zona.id, zona]));

/** A tiny real polygon per zona: the drawer's outline pass needs geometries. */
function geometriaZona(indice: number): { type: 'Polygon'; coordinates: number[][][] } {
  const dx = (indice % 10) * 0.06;
  const dy = Math.floor(indice / 10) * 0.06;
  const cx = -63.2 + dx;
  const cy = -32.4 + dy;
  return {
    type: 'Polygon',
    coordinates: [
      [
        [cx - 0.02, cy - 0.02],
        [cx + 0.02, cy - 0.02],
        [cx + 0.02, cy + 0.02],
        [cx - 0.02, cy + 0.02],
        [cx - 0.02, cy - 0.02],
      ],
    ],
  };
}

const BASINS_GEOJSON = {
  type: 'FeatureCollection',
  features: ZONAS.map((zona, indice) => ({
    type: 'Feature' as const,
    geometry: geometriaZona(indice),
    properties: { id: zona.id, nombre: zona.nombre, cuenca: zona.cuenca },
  })),
};

// ── ficha fixtures ────────────────────────────────────────────────────────────

/** Mirror of the L2 contract: online under 35 000 ha, `trabajo` beyond. */
const TOPE_ONLINE_HA = 35000;

function datasetFixture(ratio: number) {
  return {
    cobertura: 'total',
    clases: [{ clase: 'III', ha: 240.0, pct: 100.0 }],
    pixel_count: 1234,
    low_confidence: false,
    cobertura_ratio: ratio,
  };
}

const PRECIPITACION = {
  cobertura: 'total',
  low_confidence: false,
  pixel_count: 800,
  cobertura_ratio: 1,
  unidad: 'mm',
  fuente: 'CHIRPS',
  periodo: '1991-2020',
  serie: Array.from({ length: 12 }, (_, mes) => ({ mes: mes + 1, mm: 45 + mes * 3 })),
  anual_mm: 850,
};

/** The `tipo=poligono` ficha of the panel the drawer was opened from. */
const FICHA_POLIGONO = {
  tipo: 'poligono',
  area_ha: 240.0,
  suelos: datasetFixture(1),
  flood_risk: datasetFixture(0.9),
  drainage_need: datasetFixture(1),
  precipitacion_mensual: PRECIPITACION,
};

/** Stored figures per zona (`null` where nothing is stored — the dash row). */
const FIGURAS_POR_ID: Record<
  string,
  { pct: number | null; suelo: string | null; lluvia: number | null }
> = {
  'z-tercero-algodon': { pct: 23.4, suelo: 'III', lluvia: 842 },
  'z-tercero-litin': { pct: null, suelo: null, lluvia: null },
};

const FIGURA_DEFAULT = { pct: 12.5, suelo: 'II', lluvia: 900 };

// ── network mocks (registered LAST wins; the catch-all goes first) ───────────

const OPERADOR = {
  id: '00000000-0000-0000-0000-000000000002',
  email: 'operador@e2e.local',
  nombre: 'Operador',
  apellido: 'E2E',
  telefono: '',
  role: 'operador',
};

/** Storage slots `lib/auth/storage.ts` + the zustand persist cache read on boot. */
async function sembrarSesion(page: Page): Promise<void> {
  await page.addInitScript(
    ({ tokenKey, userKey, user }) => {
      window.sessionStorage.setItem(tokenKey, 'e2e-token');
      window.sessionStorage.setItem(userKey, JSON.stringify(user));
      window.localStorage.setItem(
        'cc-auth-storage',
        JSON.stringify({
          state: {
            user: { id: user.id, email: user.email },
            profile: { id: user.id, email: user.email, nombre: user.nombre, rol: user.role },
          },
          version: 0,
        })
      );
    },
    { tokenKey: 'consorcio_auth_token', userKey: 'consorcio_auth_user', user: OPERADOR }
  );
}

async function instalarMocks(page: Page): Promise<void> {
  // Generic fallback so a backend-less environment stays quiet for every call
  // this flow does not care about (registered first = lowest priority).
  await page.route('**/api/v2/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, limit: 10 }),
    })
  );

  // Session reads the boot may make: keep the seeded session untouched.
  await page.route(/\/api\/v2\/(users\/me|auth\/me)$/, (route) =>
    route.fulfill({ json: OPERADOR })
  );
  await page.route(/\/api\/v2\/auth\/jwt\/refresh/, (route) =>
    route.fulfill({ json: { access_token: 'e2e-token' } })
  );

  await page.route('**/geo/basins**', (route) => route.fulfill({ json: BASINS_GEOJSON }));

  // Geometry-only preview: areas from the fixture catalog, modo from the L2 cap.
  await page.route('**/geo/analisis-zona/preview**', async (route) => {
    const cuerpo = JSON.parse(route.request().postData() ?? '{}') as { zona_ids?: string[] };
    const ids = cuerpo.zona_ids ?? [];
    const zonas = ids.flatMap((id) => {
      const zona = ZONA_POR_ID.get(id);
      return zona ? [zona] : [];
    });
    const total = zonas.reduce((suma, zona) => suma + zona.ha, 0);
    const trabajo = total > TOPE_ONLINE_HA;
    await route.fulfill({
      json: {
        area_total_ha: total,
        area_total_ha_geodesica: Math.round(total * 1001.5) / 1000,
        subcuencas: zonas.map((zona) => ({
          id: zona.id,
          nombre: zona.nombre,
          cuenca: zona.cuenca,
          ha: zona.ha,
        })),
        fuera_de_subcuencas_ha: 0,
        modo: trabajo ? 'trabajo' : 'online',
        aviso_cap: trabajo,
      },
    });
  });

  // The ficha endpoint: the panel's `poligono` and the drawer's `zonas`.
  await page.route(/\/api\/v2\/geo\/analisis-zona(?:\?|$)/, async (route) => {
    const cuerpo = JSON.parse(route.request().postData() ?? '{}') as {
      tipo?: string;
      zona_ids?: string[];
    };
    if (cuerpo.tipo === 'zonas') {
      const ids = cuerpo.zona_ids ?? [];
      const zonas = ids.flatMap((id) => {
        const zona = ZONA_POR_ID.get(id);
        return zona ? [zona] : [];
      });
      await route.fulfill({
        json: {
          tipo: 'zonas',
          area_ha: zonas.reduce((suma, zona) => suma + zona.ha, 0),
          suelos: datasetFixture(1),
          flood_risk: datasetFixture(1),
          drainage_need: datasetFixture(0.97),
          precipitacion_mensual: PRECIPITACION,
          desglose_por_subcuenca: zonas.map((zona) => {
            const figuras = FIGURAS_POR_ID[zona.id] ?? FIGURA_DEFAULT;
            return {
              zona_id: zona.id,
              nombre: zona.nombre,
              ha: zona.ha,
              pct_alto_critico: figuras.pct,
              clase_suelo_dominante: figuras.suelo,
              lluvia_anual_mm: figuras.lluvia,
            };
          }),
          umbral_alto_critico: 'legacy70',
        },
      });
      return;
    }
    await route.fulfill({ json: FICHA_POLIGONO });
  });
}

// ── shared flow ───────────────────────────────────────────────────────────────

/**
 * Move the mouse and read MapboxDraw's mode off the map container class.
 * MapboxDraw only refreshes those classes on interaction, so every read is
 * preceded by a mousemove.
 */
async function modoDraw(page: Page): Promise<string> {
  await page.mouse.move(650, 380);
  await page.waitForTimeout(120);
  return page.evaluate(() => {
    const clase = document.querySelector('.maplibregl-map')?.className ?? '';
    return /mode-([a-z_]+)/.exec(clase)?.[1] ?? '';
  });
}

/**
 * Arm polygon tracing through the real UI.
 *
 * ⚠️ THE ENTRY HAS A PRE-EXISTING RACE (reported, not fixed — outside this
 * task's surfaces): `DrawControl` is `lazy()`, so on the FIRST arm the wiring
 * effect that calls `startDrawing()` runs while the chunk is still loading and
 * the ref is null — MapboxDraw stays in `simple_select` and canvas clicks do
 * nothing. The "Otro" dock control re-arms tracing through the ref directly,
 * which is the recovery a real user has. This helper waits for MapboxDraw's
 * mount evidence first (a `mode-*` container class), then clicks "Otro".
 */
async function armarDibujo(page: Page): Promise<boolean> {
  await page.getByRole('button', { name: 'Herramientas' }).click();
  const item = page.getByRole('menuitem', { name: 'Dibujar polígono' });
  const ofrecido = await item.waitFor({ state: 'visible', timeout: 10000 }).then(
    () => true,
    () => false
  );
  if (!ofrecido) return false;
  await item.click();

  // DrawControl mounted: MapboxDraw writes a `mode-*` class on its first
  // mousemove once its listeners are attached (the chunk + mount finished).
  let evidenciaMontaje = false;
  for (let intento = 0; intento < 40 && !evidenciaMontaje; intento += 1) {
    evidenciaMontaje = (await modoDraw(page)) !== '';
    if (!evidenciaMontaje) await page.waitForTimeout(150);
  }
  if (!evidenciaMontaje) return false;

  // "Otro" → `startDrawing()` through the (now populated) ref → draw_polygon.
  await page.getByTestId('ficha-draw-new-polygon').click();
  for (let intento = 0; intento < 20; intento += 1) {
    if ((await modoDraw(page)) === 'draw_polygon') return true;
    await page.waitForTimeout(150);
  }
  return false;
}

/**
 * Drive the REAL entry path and report whether the drawer became visible:
 * session → mocks → /mapa → Herramientas → "Dibujar polígono" → trace a
 * triangle on the canvas → ficha panel → "Informe de área".
 *
 * The polygon finishes with Enter, NOT a double-click: mapbox-gl-draw 1.5 has
 * no dblclick handler — the polygon closes on the SECOND click at the previous
 * vertex, and the trailing click of a double-click then lands on an idle map,
 * resolving "no parcel" and wiping the ficha state back to IDLE before the
 * panel can mount. Enter (`draw_polygon.onKeyUp`) finishes with no trailing
 * click. The canvas holds focus after the click sequence, so the key reaches
 * the container.
 */
async function abrirDrawer(page: Page): Promise<boolean> {
  await sembrarSesion(page);
  await instalarMocks(page);

  const reached = await page
    .goto(`${APP_URL}/mapa`, { waitUntil: 'domcontentloaded', timeout: 30000 })
    .then(
      () => true,
      () => false
    );
  if (!reached) return false;

  const montado = await page
    .getByTestId('map-workspace-root')
    .waitFor({ state: 'visible', timeout: 30000 })
    .then(
      () => true,
      () => false
    );
  if (!montado) return false;

  const canvas = page.locator('.maplibregl-canvas').first();
  const conCanvas = await canvas.waitFor({ state: 'visible', timeout: 20000 }).then(
    () => true,
    () => false
  );
  if (!conCanvas) return false;

  if (!(await armarDibujo(page))) return false;

  // Left-of-center points: the floating panels own the right side of the map.
  await canvas.click({ position: { x: 240, y: 300 } });
  await canvas.click({ position: { x: 430, y: 300 } });
  await canvas.click({ position: { x: 300, y: 420 } });
  await page.keyboard.press('Enter');

  const panel = page.getByTestId('ficha-territorial-panel');
  const panelAbierto = await panel.waitFor({ state: 'visible', timeout: 15000 }).then(
    () => true,
    () => false
  );
  if (!panelAbierto) return false;

  await page.getByTestId('informe-area-abrir').click();

  // The Drawer's data-testid lands on Mantine's root wrapper, which is a
  // full-width, HEIGHT-0 box — never "visible" for Playwright even when the
  // drawer is on screen. The Stepper inside the content section is the honest
  // visibility signal.
  return page
    .getByTestId('informe-area-stepper')
    .waitFor({ state: 'visible', timeout: 10000 })
    .then(
      () => true,
      () => false
    );
}

/** Open the drawer, switch to the Lista tab and expand one cuenca's accordion. */
async function abrirLista(page: Page, cuenca: string): Promise<void> {
  await page.getByTestId('informe-area-tabs').getByRole('tab', { name: 'Lista' }).click();

  const control = page.locator('button[data-accordion-control]', { hasText: cuenca });
  // Guard: clicking an expanded control COLLAPSES it (accordion is a toggle).
  if ((await control.getAttribute('aria-expanded')) !== 'true') {
    await control.click();
  }
  await expect(control).toHaveAttribute('aria-expanded', 'true');
}

/** Press Tab until focus lands on the first element matching `selector`. */
async function tabularHasta(page: Page, selector: string, max = 40): Promise<boolean> {
  for (let paso = 0; paso < max; paso += 1) {
    const listo = await page.evaluate(
      (sel) => document.activeElement?.matches(sel) === true,
      selector
    );
    if (listo) return true;
    await page.keyboard.press('Tab');
  }
  return false;
}

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('Informe de área — elegir dos subcuencas y ver el desglose', () => {
  test('dos subcuencas por Lista → preview online → desglose con valores por zona', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    const abierto = await abrirDrawer(page);
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    await abrirLista(page, CUENCA_TERCERO);

    // Two zonas, by their checkbox labels (the catalog names).
    await page.getByRole('checkbox', { name: 'Arroyo Algodón' }).check();
    await page.getByRole('checkbox', { name: 'Arroyo Litín' }).check();

    await expect(page.getByTestId('informe-area-contador')).toHaveText('2/60 subcuencas');
    await expect(page.getByTestId('informe-area-chip')).toHaveCount(2);

    // Revisar: totals of the union + the geodesic reference + modo online
    // (no cap alert, Generar enabled).
    await page.getByTestId('informe-area-siguiente').click();
    const total = page.getByTestId('informe-area-preview-total');
    await expect(total).toBeVisible();
    await expect(total).toHaveText('2 subcuencas · 1801.0 ha');
    await expect(page.getByTestId('informe-area-revisar')).toContainText(
      'referencia geodésica WGS84: 1803.7 ha'
    );
    await expect(page.getByTestId('informe-area-preview-cap')).toHaveCount(0);
    await expect(page.getByTestId('informe-area-generar')).toBeEnabled();

    // Generar: the desglose table — stored figures per zona, dashes where
    // nothing is stored (S8: a dash, never a fabricated 0).
    await page.getByTestId('informe-area-generar').click();
    await expect(page.getByTestId('informe-area-informe-total')).toHaveText(
      '2 subcuencas · 1801.0 ha'
    );

    const desglose = page.getByTestId('informe-area-desglose');
    const filaAlgodon = desglose.getByRole('row', { name: /Arroyo Algodón/ });
    await expect(filaAlgodon).toContainText('900.5 ha');
    await expect(filaAlgodon).toContainText('23.4%');
    await expect(filaAlgodon).toContainText('III');
    await expect(filaAlgodon).toContainText('842 mm');

    const filaLitin = desglose.getByRole('row', { name: /Arroyo Litín/ });
    await expect(filaLitin).toContainText('—');
    await expect(filaLitin).not.toContainText('0.0%');

    // The legacy70 threshold note travels with the column (decision #738).
    await expect(page.getByTestId('informe-area-drawer')).toContainText('puntaje > 70');

    // Per-dataset coverage rows render the ficha's own ratios (S5).
    await expect(page.getByTestId('informe-area-coberturas')).toContainText('100.0%');
  });

  test('modo=trabajo muestra el aviso del tope en línea y bloquea Generar', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    const abierto = await abrirDrawer(page);
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    await abrirLista(page, CUENCA_CHOCAN);
    await page.getByRole('checkbox', { name: 'Arroyo Las Mojarras' }).check();
    await page.getByRole('checkbox', { name: 'Canal Desviador' }).check();
    await page.getByTestId('informe-area-siguiente').click();

    // Preview still renders (it is geometry-only), but with the cap notice.
    await expect(page.getByTestId('informe-area-preview-total')).toHaveText(
      '2 subcuencas · 41230.0 ha'
    );
    const aviso = page.getByTestId('informe-area-preview-cap');
    await expect(aviso).toBeVisible();
    await expect(aviso).toContainText('35.000 ha');
    await expect(aviso).toContainText('PR 2');
    await expect(page.getByTestId('informe-area-generar')).toBeDisabled();
  });

  test('el flujo Elegir es operable solo con teclado (trampa de foco + selección)', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    const abierto = await abrirDrawer(page);
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    // trapFocus: Tab never escapes the drawer.
    for (let paso = 0; paso < 15; paso += 1) {
      await page.keyboard.press('Tab');
      const dentro = await page.evaluate(() => {
        const drawer = document.querySelector('[data-testid="informe-area-drawer"]');
        return drawer?.contains(document.activeElement) === true;
      });
      expect(dentro, `El foco escapó del drawer en el Tab #${paso + 1}`).toBe(true);
    }

    await abrirLista(page, CUENCA_TERCERO);

    // Keyboard path: search → accordion already open → zona checkbox → Space.
    const alBusqueda = await tabularHasta(page, '[data-testid="informe-area-busqueda"]');
    expect(alBusqueda, 'El buscador de la Lista no es alcanzable por Tab').toBe(true);
    await page.keyboard.type('algodón');

    const alCheckbox = await tabularHasta(page, '[data-testid="informe-area-zona-toggle"]');
    expect(alCheckbox, 'El checkbox de subcuenca no es alcanzable por Tab').toBe(true);
    await page.keyboard.press('Space');
    await expect(page.getByTestId('informe-area-contador')).toHaveText('1/60 subcuencas');

    const alSiguiente = await tabularHasta(page, '[data-testid="informe-area-siguiente"]');
    expect(alSiguiente, 'El botón "Revisar selección" no es alcanzable por Tab').toBe(true);
    await page.keyboard.press('Enter');

    await expect(page.getByTestId('informe-area-preview-total')).toHaveText(
      '1 subcuenca · 900.5 ha'
    );
  });

  test('p95 local: la vista previa con 60 subcuencas renderiza en menos de 1,5 s', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    test.setTimeout(240000);
    const abierto = await abrirDrawer(page);
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    const ITERACIONES = 15;
    const muestras: number[] = [];

    for (let i = 0; i < ITERACIONES; i += 1) {
      if (i > 0) {
        // Close the drawer: `cerrar` clears the selection, so every
        // iteration rebuilds a fresh 60-zona set (and its preview is a cold
        // fetch, never a TanStack cache hit).
        await page.locator('.mantine-Drawer-close').click();
        await page.getByTestId('informe-area-stepper').waitFor({ state: 'detached' });
        await page.getByTestId('informe-area-abrir').click();
        await page.getByTestId('informe-area-stepper').waitFor({ state: 'visible' });
      }

      await abrirLista(page, CUENCA_PINTO);
      await page
        .getByTestId('informe-area-lista')
        .getByRole('checkbox', { name: 'Toda la cuenca' })
        .check();

      // Vary the SET each iteration (drop Pinto 0i, add Algodón) so no two
      // iterations share a query key.
      const fuera = String((i % 60) + 1).padStart(2, '0');
      await page.getByRole('checkbox', { name: `Subcuenca Pinto ${fuera}` }).uncheck();
      await abrirLista(page, CUENCA_TERCERO);
      await page.getByRole('checkbox', { name: 'Arroyo Algodón' }).check();
      await expect(page.getByTestId('informe-area-contador')).toHaveText('60/60 subcuencas');

      const total = page.getByTestId('informe-area-preview-total');
      const inicio = Date.now();
      await page.getByTestId('informe-area-siguiente').click();
      await expect(total).toContainText('60 subcuencas', { timeout: 10000 });
      // One frame past the text so the outline/fitBounds pass is inside the
      // measured window too, not one React commit before it.
      await page.evaluate(
        () => new Promise<void>((resuelta) => requestAnimationFrame(() => resuelta()))
      );
      muestras.push(Date.now() - inicio);
    }

    muestras.sort((a, b) => a - b);
    const p95 = muestras[Math.ceil(0.95 * muestras.length) - 1];
    // Visible in the run log: what was measured, with every sample.
    // biome-ignore lint/suspicious/noConsole: the measurement IS the deliverable; it must be readable in the run log.
    console.log(
      `[informe-area p95] samples(ms)=${muestras.join(',')} p95=${p95} n=${muestras.length}`
    );
    expect(p95, `p95 ${p95} ms supera el presupuesto de 1500 ms (mocked network)`).toBeLessThan(
      1500
    );
  });
});
