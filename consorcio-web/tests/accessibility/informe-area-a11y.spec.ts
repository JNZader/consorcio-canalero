/**
 * informe-area-a11y.spec.ts — registers the informe de área view in the a11y
 * suite (T4, S6: "sin violaciones nuevas en npm run test:a11y").
 *
 * The route-based audit in a11y.spec.ts cannot reach this surface: the drawer
 * only exists behind session + network mocks + a real draw flow. This spec
 * drives the same entry path as tests/e2e/informe-area.spec.ts (see that file
 * for the full commentary on the draw mechanics), then runs axe SCOPED TO THE
 * DRAWER CONTENT — the surrounding /mapa page is out of scope here (it has its
 * own audit) and pre-existing violations elsewhere are not this change's to
 * fix.
 *
 * PR 2 added two surfaces to the drawer, both audited here: the Generar step
 * re-wired into the background-job launcher (nombre + SegmentedControl +
 * inline aria-live progress) and the «Mis informes» table (Badge estados,
 * Progress aria-hidden, download buttons). Elegir (Lista) carries over from
 * PR 1 unchanged.
 *
 * WebKit is skipped on hosts without its system libraries: the launch fails
 * before any test logic runs (pre-existing limitation of this box — see the
 * baseline note in the task report), and a skip says that honestly.
 */

import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, test } from '@playwright/test';

const OPERADOR = {
  id: '00000000-0000-0000-0000-000000000002',
  email: 'operador@e2e.local',
  nombre: 'Operador',
  apellido: 'E2E',
  telefono: '',
  role: 'operador',
};

const BASINS = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature' as const,
      geometry: {
        type: 'Polygon' as const,
        coordinates: [
          [
            [-63.22, -32.42],
            [-63.18, -32.42],
            [-63.18, -32.38],
            [-63.22, -32.38],
            [-63.22, -32.42],
          ],
        ],
      },
      properties: { id: 'z-algodon', nombre: 'Arroyo Algodón', cuenca: 'Tercero' },
    },
    {
      type: 'Feature' as const,
      geometry: {
        type: 'Polygon' as const,
        coordinates: [
          [
            [-63.16, -32.42],
            [-63.12, -32.42],
            [-63.12, -32.38],
            [-63.16, -32.38],
            [-63.16, -32.42],
          ],
        ],
      },
      properties: { id: 'z-litin', nombre: 'Arroyo Litín', cuenca: 'Tercero' },
    },
  ],
};

const dataset = {
  cobertura: 'total',
  clases: [{ clase: 'III', ha: 900.5, pct: 100.0 }],
  pixel_count: 1234,
  low_confidence: false,
  cobertura_ratio: 1,
};

const PRECIPITACION = {
  cobertura: 'total',
  low_confidence: false,
  pixel_count: 800,
  cobertura_ratio: 1,
  unidad: 'mm',
  serie: Array.from({ length: 12 }, (_, mes) => ({ mes: mes + 1, mm: 50 + mes * 3 })),
  anual_mm: 850,
};

// ── informes-area fixtures (PR 2; local wire mirror, same as the e2e spec) ────

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
    id: 'inf-a11y-1',
    nombre: 'Auditoría informe',
    estado: 'pending',
    progreso: 40,
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

/**
 * Mock `/api/v2/geo/informes-area` (registered AFTER the catch-all, so it
 * wins): the create answers 202 pending; from then on the list answers the
 * launched row plus one completed and one failed row, so the Generar audit
 * sees the inline progress and the «Mis informes» audit sees every estado
 * rendering (Badge, dash ha, stored error, enabled/disabled download).
 */
async function instalarInformesArea(page: Page): Promise<void> {
  const filas = [
    filaInforme(),
    filaInforme({
      id: 'inf-a11y-viejo',
      nombre: 'Informe viejo',
      estado: 'completed',
      progreso: 100,
      area_ha: 1801.0,
      cantidad_zonas: 2,
    }),
    filaInforme({
      id: 'inf-a11y-fallo',
      nombre: 'El que falló',
      estado: 'failed',
      error: 'GEE no disponible',
    }),
  ];
  let creo = false;

  await page.route(/\/api\/v2\/geo\/informes-area\/?$/, async (route) => {
    if (route.request().method() === 'POST') {
      creo = true;
      await route.fulfill({ status: 202, json: filaInforme() });
      return;
    }
    const items = creo ? filas : [];
    await route.fulfill({ status: 200, json: { items, total: items.length } });
  });
}

async function sembrarSesion(page: Page): Promise<void> {
  await page.addInitScript(
    ({ tokenKey, userKey, user }) => {
      window.sessionStorage.setItem(tokenKey, 'a11y-token');
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
  await page.route('**/api/v2/**', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], total: 0, page: 1, limit: 10 }),
    })
  );
  await page.route(/\/api\/v2\/(users\/me|auth\/me)$/, (route) =>
    route.fulfill({ json: OPERADOR })
  );
  await page.route(/\/api\/v2\/auth\/jwt\/refresh/, (route) =>
    route.fulfill({ json: { access_token: 'a11y-token' } })
  );
  await page.route('**/geo/basins**', (route) => route.fulfill({ json: BASINS }));
  await page.route('**/geo/analisis-zona/preview**', (route) =>
    route.fulfill({
      json: {
        area_total_ha: 1801.0,
        area_total_ha_geodesica: 1803.7,
        subcuencas: BASINS.features.map((f) => ({
          id: f.properties.id,
          nombre: f.properties.nombre,
          cuenca: f.properties.cuenca,
          ha: 900.5,
        })),
        fuera_de_subcuencas_ha: 0,
        modo: 'online',
        aviso_cap: false,
      },
    })
  );
  // Only the PANEL's `poligono` ficha is consumed after PR 2 — Generar no
  // longer fetches a `zonas` ficha (the datasets live in the PDF).
  await page.route(/\/api\/v2\/geo\/analisis-zona(?:\?|$)/, (route) =>
    route.fulfill({
      json: {
        tipo: 'poligono',
        area_ha: 240.0,
        suelos: dataset,
        flood_risk: dataset,
        drainage_need: dataset,
        precipitacion_mensual: PRECIPITACION,
      },
    })
  );
  await instalarInformesArea(page);
}

/** MapboxDraw mode read off the container class (refreshed by a mousemove). */
async function modoDraw(page: Page): Promise<string> {
  // The mousemove must land ON the canvas for MapLibre to fire map mousemove
  // events (overlays swallow the DOM event otherwise), and the /mapa layout
  // shifts the canvas per viewport — so move to the canvas's own center.
  const centro = await page
    .locator('.maplibregl-canvas')
    .first()
    .boundingBox()
    .then((caja) => (caja ? { x: caja.x + caja.width / 2, y: caja.y + caja.height / 2 } : null));
  if (centro) await page.mouse.move(centro.x, centro.y);
  await page.waitForTimeout(120);
  return page.evaluate(() => {
    const clase = document.querySelector('.maplibregl-map')?.className ?? '';
    return /mode-([a-z_]+)/.exec(clase)?.[1] ?? '';
  });
}

/** Assert the drawer content has NO critical/serious WCAG violations. */
async function auditarDrawer(page: Page, paso: string): Promise<void> {
  const resultado = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .include('.mantine-Drawer-content')
    .analyze();
  const criticos = resultado.violations.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious'
  );
  expect(
    criticos,
    `${paso}: ${JSON.stringify(
      criticos.map((v) => ({ id: v.id, nodes: v.nodes.length, help: v.help })),
      null,
      1
    )}`
  ).toHaveLength(0);
}

test.describe('Informe de área — auditoría del drawer', () => {
  test.skip(
    ({ browserName }) => browserName === 'webkit',
    'WebKit sin libs de sistema en este host'
  );

  test('Elegir (Lista), Generar (progreso) y Mis informes sin violaciones críticas o serias', async ({
    page,
  }) => {
    test.setTimeout(120000);
    await sembrarSesion(page);
    await instalarMocks(page);

    await page.goto('/mapa');
    await page.getByTestId('map-workspace-root').waitFor({ state: 'visible', timeout: 30000 });
    const canvas = page.locator('.maplibregl-canvas').first();
    // CI Firefox (sin GPU) no crea el contexto WebGL de MapLibre: el canvas
    // nunca aparece y el flujo de dibujo es imposible AHÍ. Corre donde el
    // entorno lo soporta (CI Chrome/Android, Firefox local) y salta con
    // razón donde no — mismo patrón que el skip de webkit arriba.
    const canvasVisible = await canvas
      .waitFor({ state: 'visible', timeout: 20000 })
      .then(() => true)
      .catch(() => false);
    if (!canvasVisible) {
      test.skip(
        true,
        'Sin canvas MapLibre (WebGL no disponible en este navegador/entorno — típico de CI Firefox sin GPU); el drawer se audita en Chrome/Android de CI y Firefox local'
      );
    }

    // Entry: Herramientas → Dibujar polígono → Otro (see the e2e spec for
    // why the first arm needs the "Otro" re-arm) → triangle + Enter.
    await page.getByRole('button', { name: 'Herramientas' }).click();
    await page.getByRole('menuitem', { name: 'Dibujar polígono' }).click();
    let montado = false;
    for (let intento = 0; intento < 40 && !montado; intento += 1) {
      montado = (await modoDraw(page)) !== '';
      if (!montado) await page.waitForTimeout(150);
    }
    expect(montado, 'MapboxDraw no montó (lazy DrawControl)').toBe(true);
    await page.getByTestId('ficha-draw-new-polygon').click();
    let armado = false;
    for (let intento = 0; intento < 20 && !armado; intento += 1) {
      armado = (await modoDraw(page)) === 'draw_polygon';
      if (!armado) await page.waitForTimeout(150);
    }
    expect(armado, 'draw_polygon no se armó').toBe(true);

    const caja = await canvas.boundingBox();
    expect(caja, 'canvas medible').not.toBeNull();
    const { width, height } = caja!;
    await canvas.click({ position: { x: width * 0.3, y: height * 0.45 } });
    await canvas.click({ position: { x: width * 0.6, y: height * 0.45 } });
    await canvas.click({ position: { x: width * 0.42, y: height * 0.6 } });
    await page.keyboard.press('Enter');

    await page.getByTestId('ficha-territorial-panel').waitFor({ state: 'visible', timeout: 15000 });
    await page.getByTestId('informe-area-abrir').click();
    const stepper = page.getByTestId('informe-area-stepper');
    await stepper.waitFor({ state: 'visible', timeout: 10000 });

    // Elegir with the Lista tab open: search box, accordion, checkboxes.
    await page.getByTestId('informe-area-tabs').getByRole('tab', { name: 'Lista' }).click();
    await page.locator('button[data-accordion-control]', { hasText: 'Tercero' }).click();
    await page.getByRole('checkbox', { name: 'Arroyo Algodón' }).check();
    await page.getByRole('checkbox', { name: 'Arroyo Litín' }).check();

    const contenido = page.locator('.mantine-Drawer-content');
    await expect(contenido).toBeVisible();

    await auditarDrawer(page, 'Elegir (Lista)');

    // Generar (PR 2): the launcher. Launch a real (mocked) informe so the
    // audit covers the inline aria-live progress, not just the empty form —
    // that region is the step's a11y contract (S6: estado visible anunciado).
    await page.getByTestId('informe-area-siguiente').click();
    await expect(page.getByTestId('informe-area-preview-total')).toBeVisible();
    await page.getByTestId('informe-area-generar').click();
    await page.getByTestId('informe-area-nombre').fill('Auditoría informe');
    await page.getByTestId('informe-area-crear').click();
    await expect(page.getByTestId('informe-area-progreso-inline')).toBeVisible({
      timeout: 15000,
    });
    await expect(page.getByTestId('informe-area-progreso-inline')).toContainText(
      'Generando «Auditoría informe»'
    );

    await auditarDrawer(page, 'Generar (progreso inline)');

    // «Mis informes» from the title button: the table renders every estado
    // (completed + failed + the running one), the state the buttons carry.
    await page.getByTestId('informe-area-abrir-mis-informes').click();
    const panel = page.getByTestId('informe-area-panel-mis-informes');
    await expect(panel).toBeVisible();
    await expect(page.getByTestId('informe-area-mis-informes-fila')).toHaveCount(3);

    await auditarDrawer(page, 'Mis informes (tabla)');

    // The swap back restores the flow where it was left.
    await page.getByTestId('informe-area-mis-informes-volver').click();
    await expect(page.getByTestId('informe-area-stepper')).toBeVisible();
  });
});
