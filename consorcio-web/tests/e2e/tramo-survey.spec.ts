/**
 * tramo-survey.spec.ts — flujo-caminos S4, task 4.14.
 *
 * RSS-R3's last scenario: the field form works at 390×844 WITHOUT HORIZONTAL
 * SCROLLING. An operator holds a phone on a rural road; a control that needs a
 * sideways drag to reach is a control that does not get used.
 *
 * ⚠️ GATED WITH `requireCondition`, NOT `skipForMissingData`. ⚠️
 * That choice is the point of this file. A criterion that skips itself when the
 * box it measures is absent MEASURES NOTHING — it would report green on a build
 * where the sheet never mounted at all. `requireCondition` skips only while the
 * run is blind (no `E2E_APP_URL`); the moment somebody declares an environment,
 * a missing sheet is a FAILURE, which is the honest answer.
 *
 * ⚠️ THE DATA IS STUBBED, THE LAYOUT IS REAL. ⚠️
 * The three routes this flow reads (`cruces-camino`, `cobertura`, the segment
 * detail) are fulfilled from fixtures, and the operator session is seeded into
 * the same `sessionStorage` slots the JWT adapter reads. That is deliberate:
 * what this spec measures is CSS and layout in a real browser at a real
 * viewport, and making it depend on a seeded database plus live credentials
 * would turn every honest layout regression into "no había backend". The
 * navigation it drives is the REAL one — layer toggle → panel → survey sheet —
 * so a wiring regression still fails here.
 *
 * Measurement contract: every control's `boundingBox()` is compared against the
 * SHEET BODY's own visible width (`…-sheet-body`, `MapPanelShell.tsx:281`), not
 * against the viewport. The sheet body is the element that actually overflows —
 * the sheet itself is capped by `max-height` — so it is the only box a
 * "visible without scrolling" claim can honestly be measured against.
 */

import { type Page, expect, test } from '@playwright/test';

import { APP_URL } from './helpers/mapWorkspace';
import { requireCondition } from './helpers/strictGate';

test.use({ viewport: { width: 390, height: 844 } });

const SHEET = 'tramo-survey-sheet';

/**
 * The controls RSS-R3 counts: the THREE fields plus the save action.
 *
 * `tramo-survey-estado-cuneta` is conditional — it mounts only once the
 * operator answers that the segment HAS a cuneta — so the measurement below
 * answers "Sí" first. Measuring two of the three fields and calling it "the
 * three fields fit" was the previous shape, and the third one is the one added
 * last to the layout, i.e. the one most likely to overflow it.
 */
const CONTROLS = [
  'tramo-survey-nivel',
  'tramo-survey-tiene-cuneta',
  'tramo-survey-estado-cuneta',
  'tramo-survey-save',
] as const;

/** Storage slots `lib/auth/storage.ts` reads a session from. */
const TOKEN_KEY = 'consorcio_auth_token';
const USER_KEY = 'consorcio_auth_user';

const OPERADOR = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'operador@e2e.local',
  nombre: 'Operador',
  apellido: 'E2E',
  telefono: '',
  role: 'operador',
};

const TRAMO_REF = 'RV-0001';

const CRUCES = {
  area_id: 'zona_principal',
  calculada_en: '2026-08-22T14:03:00Z',
  desactualizado: false,
  total_flujo_natural: 1,
  total_canal: 0,
  features: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [-62.68, -32.62] },
        properties: {
          id: 'c1',
          tipo: 'flujo_natural',
          tramo_ref: TRAMO_REF,
          canal_ref: null,
          direccion_flujo_deg: 90,
          rumbo_camino_deg: 0,
          lado_cruce: 'norte',
          area_aporte_ha: 12.5,
          orden_ranking: 1,
          confianza: 'alta',
          nota: null,
        },
      },
    ],
  },
  excluidos: [],
  parametros: {},
  variante: null,
  segmentos_parcialmente_cubiertos: 0,
};

const COBERTURA = {
  area_id: 'zona_principal',
  relevados: 1,
  solo_candidato: 2,
  sin_datos: 3,
  total_activos: 6,
};

/** A segment WITH a DEM candidate, so the chip and its 30 m disclosure render. */
const DETALLE = {
  tramo_ref: TRAMO_REF,
  vigente: null,
  historial: [],
  candidata: {
    tramo_ref: TRAMO_REF,
    geo_job_id: '00000000-0000-0000-0000-0000000000aa',
    dem_layer_id: null,
    clasificacion_candidata: 'terraplen',
    confianza_m: 1.4,
    calculada_en: '2026-08-20T10:00:00Z',
    nivel_sugerido: 'mayor',
  },
};

/**
 * Drive the REAL entry point: seed an operator session, stub the three reads,
 * tick the `road_flow` layer and open the survey sheet from the ranked row.
 *
 * @returns whether the survey sheet became visible.
 */
async function abrirHojaDeRelevamiento(page: Page): Promise<boolean> {
  await page.addInitScript(
    ({ tokenKey, userKey, user }) => {
      window.sessionStorage.setItem(tokenKey, 'e2e-token');
      window.sessionStorage.setItem(userKey, JSON.stringify(user));
    },
    { tokenKey: TOKEN_KEY, userKey: USER_KEY, user: OPERADOR }
  );

  await page.route('**/geo/intelligence/cruces-camino**', (route) =>
    route.fulfill({ json: CRUCES })
  );
  await page.route('**/geo/relevamiento/cobertura**', (route) =>
    route.fulfill({ json: COBERTURA })
  );
  await page.route('**/geo/relevamiento/tramos/**', (route) => route.fulfill({ json: DETALLE }));

  const reached = await page
    .goto(`${APP_URL}/mapa`)
    .then(() => true)
    .catch(() => false);
  if (!reached) return false;

  const mounted = await page
    .getByTestId('map-workspace-root')
    .waitFor({ state: 'visible', timeout: 30000 })
    .then(() => true)
    .catch(() => false);
  if (!mounted) return false;

  // Narrow viewport: the layer controls live in the burger Drawer.
  await page.getByTestId('map-workspace-burger').click();

  // The families render EXPANDED, so the accordion control is only touched when
  // the entry is actually hidden — clicking it unconditionally would COLLAPSE
  // the section and hide the very checkbox this flow needs.
  const cruces = page.getByRole('checkbox', { name: 'Cruces de camino' });
  const offered = await cruces
    .waitFor({ state: 'attached', timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  if (!offered) return false;
  if (!(await cruces.isVisible())) {
    await page.getByRole('button', { name: /Análisis/ }).click();
  }
  await cruces.check();

  // The Drawer covers the canvas; the panel it just opened is underneath it.
  await page.keyboard.press('Escape');

  const relevar = page.getByTestId(`road-flow-relevar-${TRAMO_REF}`);
  const listo = await relevar
    .waitFor({ state: 'visible', timeout: 15000 })
    .then(() => true)
    .catch(() => false);
  if (!listo) return false;

  await relevar.click();

  return page
    .getByTestId(SHEET)
    .waitFor({ state: 'visible', timeout: 15000 })
    .then(() => true)
    .catch(() => false);
}

test.describe('Relevamiento de tramo — 390×844', () => {
  test('los tres campos y el guardado entran sin scroll horizontal', async ({ page }) => {
    const mounted = await abrirHojaDeRelevamiento(page);
    requireCondition(
      mounted,
      'La hoja de relevamiento del tramo no montó desde la capa "Cruces de camino" en /mapa'
    );

    // Mount the conditional third field: "Estado de la cuneta" only exists once
    // the segment is said to HAVE one. One tap, the same one an operator makes.
    await page.getByTestId('tramo-survey-tiene-cuneta').getByText('Sí', { exact: true }).click();
    await expect(page.getByTestId('tramo-survey-estado-cuneta')).toBeVisible();

    const body = page.getByTestId(`${SHEET}-sheet-body`);
    const bodyBox = await body.boundingBox();
    requireCondition(bodyBox !== null, 'No se pudo medir la caja visible del cuerpo de la hoja');
    if (bodyBox === null) return;

    const left = bodyBox.x;
    const right = bodyBox.x + bodyBox.width;

    for (const testId of CONTROLS) {
      const control = page.getByTestId(testId);
      await expect(control, `${testId} no está visible`).toBeVisible();

      const box = await control.boundingBox();
      requireCondition(box !== null, `No se pudo medir ${testId}`);
      if (box === null) return;

      // Both edges inside the sheet body's own visible width: nothing to drag
      // sideways for. One px of tolerance for sub-pixel layout rounding.
      expect(box.x, `${testId} se sale por la izquierda`).toBeGreaterThanOrEqual(left - 1);
      expect(box.x + box.width, `${testId} se sale por la derecha`).toBeLessThanOrEqual(right + 1);
    }

    // And the body itself does not scroll sideways.
    const overflowsX = await body.evaluate((el) => el.scrollWidth > el.clientWidth + 1);
    expect(overflowsX, 'El cuerpo de la hoja tiene scroll horizontal').toBe(false);
  });

  test('cada campo muestra sus opciones a la vez (un toque por campo)', async ({ page }) => {
    const mounted = await abrirHojaDeRelevamiento(page);
    requireCondition(
      mounted,
      'La hoja de relevamiento del tramo no montó desde la capa "Cruces de camino" en /mapa'
    );

    // No keyboard, no nested menu: the options are already on screen, so the
    // count of visible radio inputs per field is the whole affordance.
    for (const [testId, expected] of [
      ['tramo-survey-nivel', 3],
      ['tramo-survey-tiene-cuneta', 3],
    ] as const) {
      const options = page.getByTestId(testId).locator('input[type="radio"]');
      await expect(options).toHaveCount(expected);
    }

    // The third field costs the same single tap once it exists.
    await page.getByTestId('tramo-survey-tiene-cuneta').getByText('Sí', { exact: true }).click();
    await expect(
      page.getByTestId('tramo-survey-estado-cuneta').locator('input[type="radio"]')
    ).toHaveCount(2);
  });
});
