import { expect, test } from '@playwright/test';
import { expectNoHorizontalOverflow } from './helpers/overflow';
import { openStableRoute } from './helpers/page';
import { touchSwipe } from './helpers/touch';

const MOBILE = { width: 360, height: 800 } as const;

test.describe('e2e mobile 360', () => {
  test.use({
    viewport: { width: MOBILE.width, height: MOBILE.height },
    hasTouch: true,
    isMobile: true,
  });

  test('participación: cambio de pestañas y stepper visible', async ({ page }) => {
    await openStableRoute(page, '/participacion', 'light', MOBILE);

    const reportes = page.getByRole('tab', { name: 'Reportar un problema' });
    const sugerencias = page.getByRole('tab', { name: 'Proponer una mejora' });

    await expect(reportes).toHaveAttribute('aria-selected', 'true');
    await expect(
      page.getByRole('group', { name: 'Paso 1: Verificar identidad, pendiente' })
    ).toBeVisible();
    await expect(
      page.getByRole('group', { name: 'Paso 2: Completar reporte, pendiente' })
    ).toBeVisible();

    await sugerencias.click();
    await expect(sugerencias).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('heading', { name: 'Enviar Sugerencia' })).toBeVisible();
    await expect(
      page.getByRole('group', { name: 'Paso 1: Verificar identidad, pendiente' })
    ).toBeVisible();
    await expect(
      page.getByRole('group', { name: 'Paso 2: Completar sugerencia, pendiente' })
    ).toBeVisible();

    await reportes.click();
    await expect(reportes).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('heading', { name: 'Nuevo Reporte' })).toBeVisible();
    await expectNoHorizontalOverflow(page);
  });

  // El mapa de la sección de ubicación (LocationSection) se construye sin
  // `cooperativeGestures`. MapLibre deja `touch-action: none` en el canvas y
  // un dedo que arranca sobre el mapa no mueve la página. Se corrige en un
  // PR posterior del plan mobile-first; hasta entonces queda en fixme para
  // que la red de seguridad no falle por un defecto ya conocido.
  // Quitar `fixme` cuando el gesto de un dedo sobre el mapa aumente
  // `window.scrollY` (la aserción de abajo ya describe ese comportamiento).
  test.fixme('participación: la sección de ubicación scrollea sin que el mapa atrape el scroll', async ({
    page,
  }) => {
    await openStableRoute(page, '/participacion', 'light', MOBILE);
    await expect(page.getByRole('heading', { name: 'Nuevo Reporte' })).toBeVisible();

    const map = page.getByRole('application', {
      name: 'Mapa interactivo para seleccionar ubicación',
    });
    const canvas = map.locator('canvas');
    await expect(canvas).toBeVisible();
    await map.evaluate((element) => {
      element.scrollIntoView({ block: 'center', behavior: 'instant' });
    });

    const before = await page.evaluate(() => ({
      y: window.scrollY,
      room: document.documentElement.scrollHeight - window.scrollY - window.innerHeight,
    }));
    expect(before.room).toBeGreaterThan(80);

    const box = await canvas.boundingBox();
    expect(box).not.toBeNull();
    if (!box) return;

    await touchSwipe(
      page,
      { x: box.x + box.width / 2, y: box.y + box.height / 2 },
      { x: box.x + box.width / 2, y: Math.max(8, box.y + box.height / 2 - 280) }
    );

    await expect
      .poll(async () => page.evaluate(() => window.scrollY))
      .toBeGreaterThan(before.y + 40);
  });

  test('login: el formulario se puede usar y no desborda en horizontal', async ({ page }) => {
    await openStableRoute(page, '/login', 'light', MOBILE);
    await expect(page.getByRole('heading', { name: 'Iniciar Sesión' })).toBeVisible();

    const email = page.getByRole('textbox', { name: 'Email' });
    const password = page.getByRole('textbox', { name: 'Contraseña' });
    await email.fill('vecino@example.com');
    await password.fill('una-clave-de-prueba');
    await expect(email).toHaveValue('vecino@example.com');
    await expect(password).toHaveValue('una-clave-de-prueba');

    const submit = page.getByRole('button', { name: 'Iniciar Sesión' });
    await expect(submit).toBeVisible();
    await expect(submit).toBeEnabled();

    for (const field of [email, password, submit]) {
      const box = await field.boundingBox();
      expect(box).not.toBeNull();
      if (!box) continue;
      expect(box.x).toBeGreaterThanOrEqual(-1);
      expect(box.x + box.width).toBeLessThanOrEqual(MOBILE.width + 1);
    }

    await expectNoHorizontalOverflow(page);
  });
});
