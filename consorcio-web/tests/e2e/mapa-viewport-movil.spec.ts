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

import { clickFixtureParcela, probeFichaAvailability } from './helpers/catastroFixture';
import { gotoMapWorkspace } from './helpers/mapWorkspace';
// El patrón nació acá y ahora vive en `helpers/strictGate.ts`, compartido con
// `mapa-maplibre.spec.ts` y `ficha-territorial.spec.ts`.
import { requireCondition, skipForMissingData } from './helpers/strictGate';

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
async function expectFitsViewport(page: import('@playwright/test').Page, viewportHeight: number) {
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
      await expect(page.getByTestId('map-workspace-root')).toHaveAttribute('data-desktop', 'false');
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
    'los controles de capa base viven en el Drawer, no flotando sobre el mapa',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      // Antes esto medía que la top bar FLOTANTE no pisara el burger. Esa barra
      // ya no existe en móvil: `MapaMapLibre` la renderiza sólo cuando
      // `useMapWorkspaceDesktop()` da true, y un teléfono acostado nunca lo da
      // (la query exige `min-height: 30.0625em`). El selector de capa base se
      // mudó al Drawer, que es lo que se afirma acá.
      await expect(page.getByTestId('map-top-bar')).toHaveCount(0);

      await page.getByTestId('map-workspace-burger').click();
      await expect(page.getByLabel('Seleccionar capa base')).toBeVisible({ timeout: 10000 });
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

  // Era `fixme` por un PRODUCT BUG que la primera corrida honesta de esta suite
  // destapó (2026-08-04): en 360×800 el canvas arrancaba en y≈442 (cabecera ≈61
  // + Paper del título + banner satelital + una top bar de 149px, porque en
  // 360px de ancho todo envuelve) y medía 500px → terminaba en y≈942, 142px
  // afuera. El rework portrait lo cierra con las mismas dos palancas que B2-2.1
  // usó en horizontal, y ninguna oculta nada:
  //   · la top bar ya no se renderiza en móvil (vive en el Drawer);
  //   · título + banner + Reportar bajan DEBAJO del mapa con `order`.
  // Presupuesto nuevo: `calc(100dvh - 96px)` = 61 cabecera + 12 py del
  // Container + 12 mb del Paper del mapa + 11 de holgura.
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
    'el título queda DEBAJO del mapa, no oculto',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      const titulo = page.getByRole('heading', { name: 'Mapa Interactivo' });
      // Nada se oculta: el reflow es `order`, no `display: none`. El banner
      // satelital y el botón Reportar viajan con él (viven en el mismo Paper).
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
    'los controles de capa base viven en el Drawer, no flotando sobre el mapa',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      const ready = await gotoMapWorkspace(page);
      requireCondition(ready, 'El shell del mapa no montó (dev server/auth no disponible)');

      // Los ~149px que la top bar flotante costaba en 360px de ancho son la
      // mitad de la deuda de altura que este bloque arregla.
      await expect(page.getByTestId('map-top-bar')).toHaveCount(0);

      await page.getByTestId('map-workspace-burger').click();
      await expect(page.getByLabel('Seleccionar capa base')).toBeVisible({ timeout: 10000 });
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
      const visible = await controls.waitFor({ state: 'visible', timeout: 10000 }).then(
        () => true,
        () => false
      );
      requireCondition(visible, 'El panel de capas no está disponible (sin datos de capas)');

      // Se mide la ETIQUETA, no el input: el input es la casilla de 28px, y lo
      // que el dedo toca (y lo que el paso 2.3 lleva a 44) es el label.
      const checkbox = controls.getByRole('checkbox').first();
      const hasCheckbox = await checkbox.waitFor({ state: 'visible', timeout: 10000 }).then(
        () => true,
        () => false
      );
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
      const hasRenderable = await renderable.waitFor({ state: 'visible', timeout: 10000 }).then(
        () => true,
        () => false
      );
      requireCondition(
        hasRenderable,
        'Sin capa vectorial renderizable (el slider solo existe con una)'
      );
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
   * B4c/T2 — el `fixme` se levanta con un fixture determinístico.
   *
   * De los tres condicionales que lo bloqueaban, DOS eran ambientales de
   * verdad (el flag `ficha_enabled` y `parcelas_catastro` cargado) y siguen
   * siendo un skip honesto vía `probeFichaAvailability`. El tercero —"que el
   * click caiga sobre una parcela"— era el frágil, y es el que
   * `helpers/catastroFixture` elimina: `/mapa?lat=&lng=&zoom=` (feature real,
   * `useReportHighlight`) centra el mapa sobre una parcela concreta del
   * dataset del repo, a 1.6 km de su borde más cercano. El porqué de esa
   * coordenada y de las alternativas descartadas está en ese archivo.
   *
   * Lo que mide: la pill `position: fixed` sigue en pantalla, el cerrar del
   * sheet llega a 44px, y la pill entra en el viewport (`scrollIntoView` en
   * `MapPanelShell`, cubierto además por `tests/unit/MapPanelMinimizePill.test.tsx`).
   */
  test(
    'la píldora sigue visible tras minimizar la ficha',
    { tag: ['@e2e', '@mapa', '@movil', '@B2-2.7'] },
    async ({ page }) => {
      // 150s, not 90: the fixture's internal waits (goto 30 + shell 30 + canvas 15 +
		// networkidle 20 + tile poll 20 + click poll 20) can legitimately sum past 90
		// on a cold environment, and a generic timeout eats the skip/fail reason the
		// helper exists to produce.
		test.setTimeout(150_000);

      const ficha = await probeFichaAvailability();
      skipForMissingData(
        ficha === 'off',
        'Ficha territorial deshabilitada o catastro vacío en el entorno'
      );
      skipForMissingData(
        ficha === 'unknown',
        'Backend no disponible para la ficha territorial (E2E_API_BASE)'
      );

      const fixture = await clickFixtureParcela(page);
      // Estructural: si en un entorno declarado no monta el shell/canvas, falla.
      requireCondition(fixture.ready, 'El shell/canvas del mapa no montó');
      // Ambiental y la red REAL (el probe de arriba mira otro backend posible):
      // sin tiles de catastro no hay parcela que clickear.
      skipForMissingData(
        !fixture.catastroTilesAvailable,
        'tiles de catastro no disponibles (Martin no sirvió parcelas en esta vista)'
      );

      // Con tiles servidos, que la ficha NO abra sí es una regresión.
      const panel = page.getByTestId('ficha-territorial-panel');
      expect(
        fixture.fichaOpened,
        'los tiles de catastro llegaron pero el click sobre la parcela no abrió la ficha'
      ).toBe(true);
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
