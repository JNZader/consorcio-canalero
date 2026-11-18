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

const FICHA_ZONAS = {
  tipo: 'zonas',
  area_ha: 1801.0,
  suelos: dataset,
  flood_risk: dataset,
  drainage_need: dataset,
  precipitacion_mensual: {
    cobertura: 'total',
    low_confidence: false,
    pixel_count: 800,
    cobertura_ratio: 1,
    unidad: 'mm',
    serie: Array.from({ length: 12 }, (_, mes) => ({ mes: mes + 1, mm: 50 + mes * 3 })),
    anual_mm: 850,
  },
  desglose_por_subcuenca: [
    {
      zona_id: 'z-algodon',
      nombre: 'Arroyo Algodón',
      ha: 900.5,
      pct_alto_critico: 23.4,
      clase_suelo_dominante: 'III',
      lluvia_anual_mm: 842,
    },
    {
      zona_id: 'z-litin',
      nombre: 'Arroyo Litín',
      ha: 900.5,
      pct_alto_critico: null,
      clase_suelo_dominante: null,
      lluvia_anual_mm: null,
    },
  ],
  umbral_alto_critico: 'legacy70',
};

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
  await page.route(/\/api\/v2\/geo\/analisis-zona(?:\?|$)/, (route) =>
    route.fulfill({
      json: {
        tipo: 'poligono',
        area_ha: 240.0,
        suelos: dataset,
        flood_risk: dataset,
        drainage_need: dataset,
        precipitacion_mensual: FICHA_ZONAS.precipitacion_mensual,
      },
    })
  );
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

test.describe('Informe de área — auditoría del drawer', () => {
  test.skip(
    ({ browserName }) => browserName === 'webkit',
    'WebKit sin libs de sistema en este host'
  );

  test('Elegir (Lista) y Generar (desglose) sin violaciones críticas o serias', async ({
    page,
  }) => {
    test.setTimeout(90000);
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

    const elegir = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .include('.mantine-Drawer-content')
      .analyze();
    const criticosElegir = elegir.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(
      criticosElegir,
      JSON.stringify(
        criticosElegir.map((v) => ({ id: v.id, nodes: v.nodes.length, help: v.help })),
        null,
        1
      )
    ).toHaveLength(0);

    // Generar: totals, coverage rows, dataset tabs and the desglose table.
    await page.getByTestId('informe-area-siguiente').click();
    await page.getByTestId('informe-area-generar').click();
    await page.getByTestId('informe-area-desglose').waitFor({ state: 'visible', timeout: 10000 });

    const generar = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .include('.mantine-Drawer-content')
      .analyze();
    const criticosGenerar = generar.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious'
    );
    expect(
      criticosGenerar,
      JSON.stringify(
        criticosGenerar.map((v) => ({ id: v.id, nodes: v.nodes.length, help: v.help })),
        null,
        1
      )
    ).toHaveLength(0);
  });
});
