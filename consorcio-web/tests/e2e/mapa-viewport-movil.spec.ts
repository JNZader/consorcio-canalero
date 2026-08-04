/**
 * mapa-viewport-movil.spec.ts — Batch 2 "móvil P1" (2.7).
 *
 * El mapa se diseñó mirando un monitor: en un teléfono el chrome vertical
 * empujaba el canvas fuera de pantalla, la píldora del panel minimizado se iba
 * con el scroll y las casillas de capas medían 16px. Los pasos 2.1 / 2.2 / 2.3
 * lo arreglaron con CSS, y `tests/unit/mapSkeletonGeometry.test.ts` +
 * `tests/unit/MapCtrlTouchTargets.test.tsx` fijan ese CSS como texto — pero
 * ninguno de los dos EJECUTA una media query. Esto sí: mide cajas reales en un
 * navegador con `pointer: coarse`.
 */

import { expect, test } from '@playwright/test';

import { gotoMapWorkspace } from './helpers/mapWorkspace';
// El patrón nació acá y ahora vive en `helpers/strictGate.ts`, compartido con
// `mapa-maplibre.spec.ts` y `ficha-territorial.spec.ts`.
import { requireCondition } from './helpers/strictGate';

/** Objetivo WCAG 2.5.5 — el mismo número que fija el test unitario del CSS. */
const TOUCH = 44;
/** `--slider-size: 14px` en coarse → Mantine calcula el thumb como el doble. */
const THUMB = 28;

/** Teléfono acostado: el caso que dispara `(orientation: landscape)`. */
const LANDSCAPE = { width: 844, height: 390 };
/** Teléfono parado y angosto: el piso de ancho que soporta el diseño. */
const PORTRAIT = { width: 360, height: 800 };

/**
 * El invariante de los pasos 2.1 / 2.2: el canvas y los controles flotantes
 * entran ENTEROS en el viewport y la página no scrollea.
 */
async function expectFitsViewport(
  page: import('@playwright/test').Page,
  viewportHeight: number
) {
  const canvas = page.getByTestId('map-workspace-canvas');
  const box = await canvas.boundingBox();
  expect(box, 'el canvas tiene que tener caja').not.toBeNull();
  if (box) {
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(viewportHeight);
  }

  // Los docks flotan SOBRE el canvas con `overflow: hidden`: lo que se pasa no
  // scrollea, se recorta.
  const docks = page.locator('.maplibregl-ctrl-group');
  for (let i = 0; i < (await docks.count()); i += 1) {
    const dock = await docks.nth(i).boundingBox();
    if (!dock) continue;
    expect(dock.y + dock.height, `dock[${i}] entra en el viewport`).toBeLessThanOrEqual(
      viewportHeight
    );
  }

  const scrollY = await page.evaluate(() => window.scrollY);
  expect(scrollY, 'la página del mapa no debería scrollear').toBe(0);
}

test.describe('Mapa en teléfono acostado (844×390)', () => {
  test.use({ viewport: LANDSCAPE, isMobile: true, hasTouch: true });

  test(
    'el navegador reporta pointer: coarse (blinda al resto de este archivo)',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      // Si esto es false, TODAS las reglas de los pasos 2.1-2.3 quedan sin
      // aplicar y los tests de abajo pasarían vacíos.
      const coarse = await page.evaluate(() => matchMedia('(pointer: coarse)').matches);
      expect(coarse).toBe(true);

      const landscape = await page.evaluate(
        () => matchMedia('(orientation: landscape) and (max-height: 30em)').matches
      );
      expect(landscape).toBe(true);
    }
  );

  test(
    'usa el modo burger, no el sidebar de escritorio',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      // 844px supera los 48em: sin la condición de alto de `MapWorkspace` esto
      // sería 'true', y la top bar flotante taparía la cabecera del sidebar (con
      // el panel colapsado, el botón de expandir queda cubierto y el panel es
      // irrecuperable).
      await expect(page.getByTestId('map-workspace-root')).toHaveAttribute(
        'data-desktop',
        'false'
      );
      await expect(page.getByTestId('map-workspace-burger')).toBeVisible();
    }
  );

  test(
    'el canvas y los controles entran en el viewport sin scroll',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      await expectFitsViewport(page, LANDSCAPE.height);
    }
  );

  test(
    'el título queda DEBAJO del mapa, no oculto',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      const titulo = page.getByRole('heading', { name: 'Mapa Interactivo' });
      // Nada se oculta: el reflow es `order`, no `display: none`.
      await expect(titulo).toBeVisible();

      const canvas = await page.getByTestId('map-workspace-canvas').boundingBox();
      const heading = await titulo.boundingBox();
      expect(canvas, 'el canvas tiene caja').not.toBeNull();
      expect(heading, 'el título tiene caja').not.toBeNull();
      if (canvas && heading) {
        expect(heading.y).toBeGreaterThan(canvas.y);
      }
    }
  );

  test(
    'la top bar flotante no pisa el burger',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      const burger = await page.getByTestId('map-workspace-burger').boundingBox();
      const topBar = await page.getByTestId('map-top-bar').boundingBox();
      expect(burger, 'el burger tiene caja').not.toBeNull();
      expect(topBar, 'la top bar tiene caja').not.toBeNull();
      if (burger && topBar) {
        // `left: calc(spacing-sm + 44px + 8px)` — la top bar arranca a la
        // derecha de la caja táctil del burger.
        expect(topBar.x).toBeGreaterThanOrEqual(burger.x + burger.width);
      }
    }
  );
});

test.describe('Mapa en teléfono parado (360×800)', () => {
  test.use({ viewport: PORTRAIT, isMobile: true, hasTouch: true });

  test(
    'el navegador reporta pointer: coarse (blinda al resto de este archivo)',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      const coarse = await page.evaluate(() => matchMedia('(pointer: coarse)').matches);
      expect(coarse).toBe(true);
      // Parado NO entra en la query de landscape: el canvas conserva su
      // presupuesto de alto normal.
      const landscape = await page.evaluate(
        () => matchMedia('(orientation: landscape) and (max-height: 30em)').matches
      );
      expect(landscape).toBe(false);
    }
  );

  test(
    'el canvas y los controles entran en el viewport sin scroll',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      await expectFitsViewport(page, PORTRAIT.height);
    }
  );

  test(
    'las filas de capas y el thumb del slider llegan a los tamaños táctiles',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      // En angosto los controles viven en un Drawer detrás del burger.
      const burger = page.getByTestId('map-workspace-burger');
      if (await burger.isVisible().catch(() => false)) await burger.click();

      const controls = page.getByRole('region', { name: 'Controles de capas del mapa' });
      const visible = await controls.isVisible({ timeout: 10000 }).catch(() => false);
      requireCondition(visible, 'El panel de capas no está disponible (sin datos de capas)');

      // Se mide la ETIQUETA, no el input: el input es la casilla de 28px, y lo
      // que el dedo toca (y lo que el paso 2.3 lleva a 44) es el label.
      const checkbox = controls.getByRole('checkbox').first();
      const hasCheckbox = await checkbox.isVisible({ timeout: 10000 }).catch(() => false);
      requireCondition(hasCheckbox, 'Sin filas de capas en este entorno');

      const inputId = await checkbox.getAttribute('id');
      const label = inputId
        ? controls.locator(`label[for="${inputId}"]`)
        : controls.locator('label').first();
      const labelBox = await label.boundingBox();
      expect(labelBox, 'la etiqueta de la casilla tiene caja').not.toBeNull();
      if (labelBox) expect(labelBox.height).toBeGreaterThanOrEqual(TOUCH);

      // El thumb del slider MEDIDO de verdad. Es el único de los cuatro
      // controles cuyo tamaño Mantine escribe inline (`size` está en sus
      // `defaultProps`), así que la regla lleva `!important` — y si ese
      // `!important` se cae, esto lo caza y el test de CSS no.
      const renderable = controls
        .getByRole('checkbox', { name: /Suelos|Catastro|Hidrografía|Red vial|Subcuencas/i })
        .first();
      const hasRenderable = await renderable.isVisible({ timeout: 10000 }).catch(() => false);
      requireCondition(hasRenderable, 'Sin capa vectorial renderizable (el slider solo existe con una)');
      await renderable.check();

      const thumb = controls.getByRole('slider').first();
      await expect(thumb).toBeVisible({ timeout: 10000 });
      const thumbBox = await thumb.boundingBox();
      expect(thumbBox, 'el thumb del slider tiene caja').not.toBeNull();
      if (thumbBox) {
        expect(thumbBox.height).toBeGreaterThanOrEqual(THUMB);
        expect(thumbBox.width).toBeGreaterThanOrEqual(THUMB);
      }
    }
  );

  /**
   * FIXME a propósito, NO skip.
   *
   * Abrir la ficha necesita tres cosas que este spec no puede garantizar: el
   * flag `ficha_enabled` del backend, `parcelas_catastro` cargado, y que un
   * click al centro del canvas caiga sobre una parcela (ver
   * `ficha-territorial.spec.ts`, que por eso mismo skipea en tres puntos). Un
   * `skip` encadenado a esos tres condicionales sería exactamente el "verde
   * vacío" que este archivo trata de evitar: un fixme se ve en el reporte y
   * pide un fixture determinístico de catastro antes de poder afirmar nada.
   *
   * Lo que quedaría por medir: la pill `position: fixed` sigue en pantalla con
   * la página scrolleada, el cerrar del sheet llega a 44px, y restaurar trae el
   * canvas a cuadro (`scrollIntoView` en `MapPanelShell`, cubierto hoy por
   * `tests/unit/MapPanelMinimizePill.test.tsx`).
   */
  test.fixme(
    'la píldora sigue visible tras minimizar la ficha (necesita fixture de catastro)',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó');

      const panel = page.getByTestId('ficha-territorial-panel');
      await expect(panel).toBeVisible();

      const close = page.getByTestId('ficha-territorial-panel-sheet-close');
      const closeBox = await close.boundingBox();
      if (closeBox) expect(closeBox.height).toBeGreaterThanOrEqual(TOUCH);

      await page.getByTestId('ficha-territorial-panel-minimize').click();

      const pill = page.getByTestId('ficha-territorial-panel-pill');
      await expect(pill).toBeVisible();
      const pillBox = await pill.boundingBox();
      if (pillBox) {
        expect(pillBox.y + pillBox.height).toBeLessThanOrEqual(PORTRAIT.height);
        expect(pillBox.height).toBeGreaterThanOrEqual(40);
      }
    }
  );
});
