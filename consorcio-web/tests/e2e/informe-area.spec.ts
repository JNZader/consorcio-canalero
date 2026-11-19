/**
 * informe-area.spec.ts — informe de área PR 1 (T4) + PR 2 (T4, flujo en
 * segundo plano).
 *
 * PR 1's acceptance scenario (pick subcuencas from the ficha panel's
 * "Informe de área" flow) still owns Elegir/Revisar; PR 2 re-wired Generar
 * into the LAUNCHER of a background job, so this suite now drives the whole
 * wire contract: create POST 202 → polled list transitions
 * (pending→running→completed) → "Informe listo" → Descargar PDF with the
 * server's filename, plus the desde_cache instant path, the failed row with
 * "Volver a intentar", the 150.000 ha cap copy and the «Mis informes»
 * table. Keyboard operability of Elegir and the 60-subcuenca preview render
 * budget (p95 < 1,5 s, mocked network) carry over from PR 1 unchanged.
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

/** Two small zonas for the happy path, two big ones for the cap copy, 60 for the p95. */
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

// ── informes-area fixtures (PR 2) ─────────────────────────────────────────────

/**
 * Local mirror of `InformeAreaItem` (`lib/api/informesArea.ts` ←
 * `schemas.InformeAreaResponse`). The spec does NOT import types from src on
 * purpose: the fixture is the wire contract, same discipline as ZonaFixture —
 * if the shape drifts, this mirror must be edited by hand and the diff says so.
 */
interface InformeFila {
  readonly id: string;
  readonly nombre: string;
  readonly estado: 'pending' | 'running' | 'completed' | 'failed';
  readonly progreso: number;
  readonly desde_cache: boolean;
  readonly area_ha: number | null;
  readonly cantidad_zonas: number;
  readonly error: string | null;
  readonly vence_at: string;
  readonly created_at: string;
  readonly updated_at: string;
}

function filaInforme(parciales: Partial<InformeFila> = {}): InformeFila {
  return {
    id: 'inf-e2e-1',
    nombre: 'Informe Tercero norte',
    estado: 'pending',
    progreso: 0,
    desde_cache: false,
    area_ha: null,
    cantidad_zonas: 0,
    error: null,
    vence_at: '2027-02-16T12:00:00Z',
    created_at: '2026-11-18T12:00:00Z',
    updated_at: '2026-11-18T12:00:00Z',
    ...parciales,
  };
}

/** Bytes with a real PDF signature: the download must cross the wire (parity). */
const PDF_E2E = Buffer.from(
  '%PDF-1.4\n%âãÏÓ\n(informe de área e2e)\ntrailer\n<<>>\n%%EOF\n',
  'binary'
);

/**
 * The disposition `service._nombre_archivo` builds: ASCII slug half + RFC 5987
 * half with the original Spanish spelling. The client prefers the UTF-8 half,
 * so the browser's suggested filename must be the es-AR name, not the slug.
 */
const DISPOSITION_E2E =
  'attachment; filename="informe-tercero-norte.pdf"; filename*=UTF-8\'\'Informe%20Tercero%20norte.pdf';

interface CreacionCapturada {
  readonly nombre: string;
  readonly zona_ids: readonly string[];
  readonly desglose: boolean;
  readonly authorization: string | null;
}

interface PeticionesInformes {
  readonly creaciones: readonly CreacionCapturada[];
  readonly pdfs: ReadonlyArray<{ authorization: string | null; url: string }>;
  listados: number;
}

interface OpcionesInformes {
  /** Rows the GET list answers BEFORE any create (drawer mount). Default: none. */
  readonly alMontar?: readonly InformeFila[];
  /** POST create responses by call number (1-based; the LAST one repeats). */
  readonly crear: ReadonlyArray<InformeFila>;
  /**
   * Rows the GET list answers after create #n, `ms` ms after the LAST create.
   *
   * Sequenced by TIME, not by call ordinal: the dev server runs React
   * StrictMode (double mount → an extra list GET), and an ordinal sequence
   * would silently shift one phase. A wrong phase here shows up as a wrong
   * estado on screen, which the UI assertions catch.
   */
  readonly listar: (n: number, ms: number) => readonly InformeFila[];
}

/**
 * Mock the whole `/api/v2/geo/informes-area` surface: the collection route
 * (POST create 202 / GET list) and the PDF download. Must be registered AFTER
 * `instalarMocks` (later registration wins over its catch-all) and BEFORE
 * navigation — pass it to `abrirDrawer` as `extra`, which guarantees both.
 */
async function instalarInformesArea(
  page: Page,
  opciones: OpcionesInformes
): Promise<PeticionesInformes> {
  // The INTERFACE is readonly (callers must not mutate); the handler fills
  // mutable arrays behind it. `nCreaciones` counts create CALLS (the ordinal
  // the mock sequences on); `registro.creaciones` is the captured bodies.
  const creacionesCapturadas: CreacionCapturada[] = [];
  const pdfsCapturados: { authorization: string | null; url: string }[] = [];
  const registro: PeticionesInformes = {
    creaciones: creacionesCapturadas,
    pdfs: pdfsCapturados,
    listados: 0,
  };
  let nCreaciones = 0;
  let ultimaCreacion = 0;

  await page.route('**/api/v2/geo/informes-area/*/pdf', async (route) => {
    pdfsCapturados.push({
      authorization: route.request().headers().authorization ?? null,
      url: route.request().url(),
    });
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'application/pdf',
        'Content-Disposition': DISPOSITION_E2E,
      },
      body: PDF_E2E,
    });
  });

  await page.route(/\/api\/v2\/geo\/informes-area\/?$/, async (route) => {
    const peticion = route.request();
    if (peticion.method() === 'POST') {
      nCreaciones += 1;
      ultimaCreacion = Date.now();
      const cuerpo = JSON.parse(peticion.postData() ?? '{}') as {
        nombre?: string;
        zona_ids?: string[];
        desglose?: boolean;
      };
      creacionesCapturadas.push({
        nombre: cuerpo.nombre ?? '',
        zona_ids: [...(cuerpo.zona_ids ?? [])],
        desglose: cuerpo.desglose ?? true,
        authorization: peticion.headers().authorization ?? null,
      });
      const fila = opciones.crear[Math.min(nCreaciones - 1, opciones.crear.length - 1)];
      await route.fulfill({ status: 202, json: fila });
      return;
    }
    registro.listados += 1;
    const filas =
      nCreaciones === 0
        ? (opciones.alMontar ?? [])
        : opciones.listar(nCreaciones, Date.now() - ultimaCreacion);
    await route.fulfill({ status: 200, json: { items: filas, total: filas.length } });
  });

  return registro;
}

/** Drive Elegir → Revisar → Generar (the launcher form) inside an open drawer. */
async function llegarAGenerar(page: Page, cuenca: string, zonas: string[]): Promise<void> {
  await abrirLista(page, cuenca);
  for (const zona of zonas) {
    await page.getByRole('checkbox', { name: zona }).check();
  }
  await page.getByTestId('informe-area-siguiente').click();
  await expect(page.getByTestId('informe-area-preview-total')).toBeVisible();
  await page.getByTestId('informe-area-generar').click();
  await expect(page.getByTestId('informe-area-nombre')).toBeVisible();
}

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
  await page.route('**/geo/informes-area/preview**', async (route) => {
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

  // The ficha endpoint: only the PANEL's `poligono` shape is still consumed
  // after PR 2 — the drawer's Generar step no longer fetches a `zonas` ficha
  // (the datasets live in the 7-section PDF now).
  await page.route(/\/api\/v2\/geo\/analisis-zona(?:\?|$)/, (route) =>
    route.fulfill({ json: FICHA_POLIGONO })
  );
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
 * `extra` installs ADDITIONAL routes (the informes-area surface) between the
 * base mocks and the navigation: after `instalarMocks` (so the catch-all does
 * not swallow them) and before `goto` (so no request races the install).
 *
 * The polygon finishes with Enter, NOT a double-click: mapbox-gl-draw 1.5 has
 * no dblclick handler — the polygon closes on the SECOND click at the previous
 * vertex, and the trailing click of a double-click then lands on an idle map,
 * resolving "no parcel" and wiping the ficha state back to IDLE before the
 * panel can mount. Enter (`draw_polygon.onKeyUp`) finishes with no trailing
 * click. The canvas holds focus after the click sequence, so the key reaches
 * the container.
 */
async function abrirDrawer(
  page: Page,
  extra?: (page: Page) => Promise<void>
): Promise<boolean> {
  await sembrarSesion(page);
  await instalarMocks(page);
  if (extra) await extra(page);

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

test.describe('Informe de área — elegir, lanzar en segundo plano y descargar', () => {
  test('dos subcuencas por Lista → create 202 → poll pending/running/completed → Informe listo → Descargar PDF', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    test.setTimeout(120000);
    let registro!: PeticionesInformes;
    const abierto = await abrirDrawer(page, async (p) => {
      registro = await instalarInformesArea(p, {
        crear: [filaInforme()],
        // Time-based phases: <4 s pending, <8 s running, then completed. The
        // hook polls every 5 s, so each poll lands in the next phase.
        listar: (_n, ms) => {
          if (ms < 4000) return [filaInforme({ estado: 'pending', progreso: 0 })];
          if (ms < 8000) return [filaInforme({ estado: 'running', progreso: 40 })];
          return [
            filaInforme({
              estado: 'completed',
              progreso: 100,
              area_ha: 1801.0,
              cantidad_zonas: 2,
            }),
          ];
        },
      });
    });
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    await llegarAGenerar(page, CUENCA_TERCERO, ['Arroyo Algodón', 'Arroyo Litín']);

    // Revisar: totals of the union + the geodesic reference + modo online.
    // (llegarAGenerar already passed through it; the totals live here too.)
    // The create button stays locked until a nombre exists — a nameless create
    // would only spend a rate-limit slot on a guaranteed 422.
    await expect(page.getByTestId('informe-area-crear')).toBeDisabled();
    await expect(page.getByRole('radio', { name: 'Total y subcuencas' })).toBeChecked();

    await page.getByTestId('informe-area-nombre').fill('Informe Tercero norte');
    await page.getByTestId('informe-area-crear').click();

    // The wire contract of the create (S2): nombre, the picked zonas, the
    // SegmentedControl's depth, and the bearer in the header — never the URL.
    await expect
      .poll(() => registro.creaciones.length, { timeout: 15000 })
      .toBe(1);
    const [creado] = registro.creaciones;
    expect(creado.nombre).toBe('Informe Tercero norte');
    expect([...creado.zona_ids].sort()).toEqual(['z-tercero-algodon', 'z-tercero-litin']);
    expect(creado.desglose).toBe(true);
    expect(creado.authorization).toBe('Bearer e2e-token');

    // Inline progress (aria-live) walks the polled estados: 0 % → 40 %.
    const progreso = page.getByTestId('informe-area-progreso-inline');
    await expect(progreso).toBeVisible({ timeout: 15000 });
    await expect(progreso).toContainText('Generando «Informe Tercero norte»');
    await expect(progreso).toContainText('Te avisamos cuando esté');
    await expect(progreso).toContainText('0%', { timeout: 15000 });
    await expect(progreso).toContainText('40%', { timeout: 15000 });

    // …until the list answers completed: the ready panel with the row's totals.
    const listo = page.getByTestId('informe-area-listo-inline');
    await expect(listo).toBeVisible({ timeout: 20000 });
    await expect(listo).toContainText('2 subcuencas');
    await expect(listo).toContainText('1801.0 ha');

    // Descargar PDF: a REAL download event whose suggested filename is the
    // server's RFC 5987 half (es-AR spelling), and whose bytes crossed the
    // wire — parity, same discipline as the rainfall exports.
    const descargaPrometida = page.waitForEvent('download');
    await page.getByTestId('informe-area-descargar-inline').click();
    const descarga = await descargaPrometida;
    expect(descarga.suggestedFilename()).toBe('Informe Tercero norte.pdf');

    const flujo = await descarga.createReadStream();
    const partes: Buffer[] = [];
    for await (const parte of flujo) partes.push(parte as Buffer);
    expect(Buffer.concat(partes).toString('binary')).toContain('%PDF');

    expect(registro.pdfs.length).toBe(1);
    expect(registro.pdfs[0].authorization).toBe('Bearer e2e-token');
    expect(registro.pdfs[0].url).not.toContain('e2e-token');
  });

  test('modo=trabajo anuncia el camino en segundo plano (150.000) y Generar queda habilitado', {
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

    // Preview still renders (geometry-only); the cap notice now SELLS the
    // background path instead of blocking (PR 2: every selection up to
    // 150.000 ha generates).
    await expect(page.getByTestId('informe-area-preview-total')).toHaveText(
      '2 subcuencas · 41230.0 ha'
    );
    const aviso = page.getByTestId('informe-area-preview-cap');
    await expect(aviso).toBeVisible();
    await expect(aviso).toContainText('35.000 ha');
    await expect(aviso).toContainText('150.000');
    await expect(aviso).toContainText('segundo plano');
    await expect(page.getByTestId('informe-area-generar')).toBeEnabled();

    // 41.230 ha is big but under the informe cap: the launcher accepts it —
    // no client-side tope alert, crear enabled once the nombre exists.
    await page.getByTestId('informe-area-generar').click();
    await expect(page.getByTestId('informe-area-tope')).toHaveCount(0);
    await expect(page.getByTestId('informe-area-crear')).toBeDisabled();
    await page.getByTestId('informe-area-nombre').fill('Chocancharava completa');
    await expect(page.getByTestId('informe-area-crear')).toBeEnabled();
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

  test('desde_cache: 202 con cache hit → descarga inmediata del PDF, sin sondeo', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    test.setTimeout(120000);
    const filaCache = filaInforme({
      estado: 'completed',
      progreso: 100,
      desde_cache: true,
      area_ha: 1801.0,
      cantidad_zonas: 2,
    });
    let registro!: PeticionesInformes;
    const abierto = await abrirDrawer(page, async (p) => {
      registro = await instalarInformesArea(p, {
        crear: [filaCache],
        listar: () => [filaCache],
      });
    });
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    await llegarAGenerar(page, CUENCA_TERCERO, ['Arroyo Algodón', 'Arroyo Litín']);
    await page.getByTestId('informe-area-nombre').fill('Informe Tercero norte');

    // The download is AUTOMATIC on a cache hit — armed before the create.
    const descargaPrometida = page.waitForEvent('download');
    await page.getByTestId('informe-area-crear').click();

    // No polling UI ever: the ready panel replaces the progress inline.
    const listo = page.getByTestId('informe-area-listo-inline');
    await expect(listo).toBeVisible({ timeout: 15000 });
    await expect(listo).toContainText('1801.0 ha');
    await expect(page.getByTestId('informe-area-progreso-inline')).toHaveCount(0);

    // The contract's fork: the cache-hit toast, not "Te avisamos cuando esté".
    await expect(page.getByText('El informe ya estaba listo')).toBeVisible();

    const descarga = await descargaPrometida;
    expect(descarga.suggestedFilename()).toBe('Informe Tercero norte.pdf');
    expect(registro.pdfs.length).toBe(1);

    // NO polling: once every row is terminal the list query stops reading.
    // Settle past the create's invalidation refetch, then outwait one full
    // 5 s poll cycle and demand the count did not move.
    await expect
      .poll(() => registro.listados, { timeout: 15000 })
      .toBeGreaterThanOrEqual(2);
    const listadosTrasCreacion = registro.listados;
    await page.waitForTimeout(6500);
    expect(registro.listados, 'el listado siguió sondeando con todas las filas terminales').toBe(
      listadosTrasCreacion
    );
  });

  test('un informe que falla deja el motivo guardado y «Volver a intentar» re-crea', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    test.setTimeout(120000);
    let registro!: PeticionesInformes;
    const abierto = await abrirDrawer(page, async (p) => {
      registro = await instalarInformesArea(p, {
        // Two creates: the initial launch and the retry.
        crear: [filaInforme(), filaInforme()],
        listar: (n, ms) => {
          if (n === 1) {
            return ms < 4000
              ? [filaInforme({ estado: 'pending', progreso: 0 })]
              : [filaInforme({ estado: 'failed', error: 'GEE no disponible' })];
          }
          // The retry succeeds: completed as soon as the invalidation lands.
          return [
            filaInforme({
              estado: 'completed',
              progreso: 100,
              area_ha: 1801.0,
              cantidad_zonas: 2,
            }),
          ];
        },
      });
    });
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    await llegarAGenerar(page, CUENCA_TERCERO, ['Arroyo Algodón', 'Arroyo Litín']);
    await page.getByTestId('informe-area-nombre').fill('Informe Tercero norte');
    await page.getByTestId('informe-area-crear').click();

    // First pending shows, then the polled failed row flips the panel with the
    // STORED readable reason (S8) and the remedy that exists here: re-create.
    await expect(page.getByTestId('informe-area-progreso-inline')).toBeVisible({
      timeout: 15000,
    });
    const fallo = page.getByTestId('informe-area-fallo-inline');
    await expect(fallo).toBeVisible({ timeout: 20000 });
    await expect(fallo).toContainText('GEE no disponible');
    await expect(fallo).toContainText('No se pudo generar el informe');

    await fallo.getByRole('button', { name: 'Volver a intentar' }).click();
    await expect
      .poll(() => registro.creaciones.length, { timeout: 15000 })
      .toBe(2);
    await expect(page.getByTestId('informe-area-listo-inline')).toBeVisible({
      timeout: 15000,
    });
  });

  test('«Mis informes» desde el drawer: filas por estado y descarga solo en completed', {
    tag: ['@e2e', '@medium', '@mapa', '@informe-area'],
  }, async ({ page }) => {
    test.setTimeout(90000);
    const filas = [
      filaInforme({
        id: 'inf-viejo',
        nombre: 'Viejo confiable',
        estado: 'completed',
        progreso: 100,
        area_ha: 2400.5,
        cantidad_zonas: 1,
      }),
      filaInforme({ id: 'inf-curso', nombre: 'Trabajo en curso', estado: 'running', progreso: 35 }),
      filaInforme({ id: 'inf-fallo', nombre: 'El que falló', estado: 'failed', error: 'GEE no disponible' }),
    ];
    const abierto = await abrirDrawer(page, async (p) => {
      await instalarInformesArea(p, {
        alMontar: filas,
        crear: [filaInforme()],
        listar: () => filas,
      });
    });
    requireCondition(
      abierto,
      'El drawer del informe de área no abrió desde el botón del panel de la ficha'
    );

    // The title button swaps the Stepper for the table; the flow survives.
    await page.getByTestId('informe-area-abrir-mis-informes').click();
    const panel = page.getByTestId('informe-area-panel-mis-informes');
    await expect(panel).toBeVisible();
    await expect(page.getByTestId('informe-area-stepper')).toHaveCount(0);
    await expect(panel).toContainText('90 días');

    const tabla = page.getByTestId('informe-area-mis-informes');
    await expect(tabla).toBeVisible();
    await expect(tabla.getByTestId('informe-area-mis-informes-fila')).toHaveCount(3);

    // Completed: ha present (never a fabricated 0), Listo badge, download ON.
    const filaViejo = tabla.getByRole('row', { name: /Viejo confiable/ });
    await expect(filaViejo).toContainText('2400.5 ha');
    await expect(filaViejo).toContainText('Listo');
    await expect(
      filaViejo.getByTestId('informe-area-mis-informes-descarga')
    ).toBeEnabled();

    // In course: ha is a dash until `resultado` exists, download OFF.
    const filaCurso = tabla.getByRole('row', { name: /Trabajo en curso/ });
    await expect(filaCurso).toContainText('Generando');
    await expect(filaCurso).toContainText('35%');
    await expect(
      filaCurso.getByTestId('informe-area-mis-informes-descarga')
    ).toBeDisabled();

    // Failed: the stored reason under the nombre, download OFF.
    const filaFallo = tabla.getByRole('row', { name: /El que falló/ });
    await expect(filaFallo).toContainText('Falló');
    await expect(filaFallo).toContainText('GEE no disponible');
    await expect(
      filaFallo.getByTestId('informe-area-mis-informes-descarga')
    ).toBeDisabled();

    // Back to the flow: the Stepper returns (state survived underneath).
    await page.getByTestId('informe-area-mis-informes-volver').click();
    await expect(page.getByTestId('informe-area-stepper')).toBeVisible();
  });
});
