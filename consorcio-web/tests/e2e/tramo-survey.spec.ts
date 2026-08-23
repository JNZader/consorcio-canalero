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
 * Measurement contract: every control's `boundingBox()` is compared against the
 * SHEET BODY's own visible width (`…-sheet-body`, `MapPanelShell.tsx:281`), not
 * against the viewport. The sheet body is the element that actually overflows —
 * the sheet itself is capped by `max-height` — so it is the only box a
 * "visible without scrolling" claim can honestly be measured against.
 */

import { expect, test } from '@playwright/test';

import { APP_URL } from './helpers/mapWorkspace';
import { requireCondition } from './helpers/strictGate';

test.use({ viewport: { width: 390, height: 844 } });

const SHEET = 'tramo-survey-sheet';

/** The controls RSS-R3 counts: three fields plus the save action. */
const CONTROLS = ['tramo-survey-nivel', 'tramo-survey-tiene-cuneta', 'tramo-survey-save'] as const;

test.describe('Relevamiento de tramo — 390×844', () => {
  test('los tres campos y el guardado entran sin scroll horizontal', async ({ page }) => {
    await page.goto(`${APP_URL}/mapa`);

    const sheet = page.getByTestId(SHEET);
    const mounted = await sheet
      .waitFor({ state: 'visible', timeout: 15000 })
      .then(() => true)
      .catch(() => false);
    requireCondition(
      mounted,
      'La hoja de relevamiento del tramo no montó: no hay punto de entrada en /mapa'
    );

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
    await page.goto(`${APP_URL}/mapa`);

    const sheet = page.getByTestId(SHEET);
    const mounted = await sheet
      .waitFor({ state: 'visible', timeout: 15000 })
      .then(() => true)
      .catch(() => false);
    requireCondition(
      mounted,
      'La hoja de relevamiento del tramo no montó: no hay punto de entrada en /mapa'
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
  });
});
