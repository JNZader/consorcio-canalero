import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Locator, type Page } from '@playwright/test';

const ROUTES = [
  { path: '/', name: 'Homepage' },
  { path: '/mapa', name: 'Mapa Interactivo' },
  { path: '/reportes', name: 'Formulario de Reportes' },
  { path: '/dashboard', name: 'Dashboard' },
  { path: '/login', name: 'Login' },
] as const;

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa'] as const;
const CRITICAL_IMPACTS = new Set(['critical', 'serious']);

async function gotoAndWait(page: Page, path: string) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await page.locator('#main-content').waitFor({ state: 'attached' });
}

async function expectLabelsForInputs(page: Page, selector: string) {
  const inputs = await page.locator(selector).all();

  for (const input of inputs) {
    const type = await input.getAttribute('type');
    if (type === 'hidden' || !(await input.isVisible())) {
      continue;
    }

    const id = await input.getAttribute('id');
    const ariaLabel = await input.getAttribute('aria-label');
    const ariaLabelledby = await input.getAttribute('aria-labelledby');
    let hasLabel = Boolean(ariaLabel || ariaLabelledby);

    if (!hasLabel && id) {
      hasLabel = (await page.locator(`label[for="${id}"]`).count()) > 0;
    }

    expect(hasLabel).toBe(true);
  }
}

async function expectVisibleIfAny(locator: Locator) {
  if ((await locator.count()) > 0) {
    await expect(locator).toBeVisible();
  }
}

test.describe('Auditoria de Accesibilidad WCAG 2.1 AA', () => {
  test.describe.configure({ mode: 'parallel' });

  for (const route of ROUTES) {
    test(`${route.name} - sin violaciones automaticas criticas o serias`, async ({ page }) => {
      await gotoAndWait(page, route.path);

      const results = await new AxeBuilder({ page }).withTags([...WCAG_TAGS]).analyze();
      const criticalViolations = results.violations.filter((violation) =>
        violation.impact ? CRITICAL_IMPACTS.has(violation.impact) : false
      );

      expect(criticalViolations).toHaveLength(0);
    });
  }
});

test.describe('Skip Links', () => {
  test('skip link es visible al enfocar y navega al contenido principal', async ({ page }) => {
    await gotoAndWait(page, '/');
    await page.keyboard.press('Tab');

    const skipLink = page.locator('.skip-link');
    await expect(skipLink).toBeVisible();
    await expect(skipLink).toHaveText(/saltar/i);

    await page.keyboard.press('Enter');
    await expect(page.locator('#main-content')).toBeFocused();
  });
});

test.describe('Navegacion por teclado', () => {
  test('elementos interactivos, menu movil, radios y menubar son accesibles', async ({ page }) => {
    await gotoAndWait(page, '/');

    const focusableElements = await page
      .locator('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')
      .all();
    expect(focusableElements.length).toBeGreaterThan(0);

    for (const element of focusableElements.slice(0, 6)) {
      await element.focus();
      await expect(element).toBeFocused();
    }

    await page.setViewportSize({ width: 375, height: 667 });
    await gotoAndWait(page, '/');
    const burger = page.getByRole('button', { name: /abrir menu/i });
    await burger.click();

    const drawer = page.locator('.mantine-Drawer-content');
    await expect(drawer).toBeVisible();
    await page.keyboard.press('Tab');
    const isInDrawer = await page
      .locator(':focus')
      .evaluate((el) => el.closest('.mantine-Drawer-content') !== null);
    expect(isInDrawer).toBe(true);
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible();

    await gotoAndWait(page, '/reportes');
    const radios = page.locator('[role="radio"]');
    if ((await radios.count()) >= 2) {
      const firstRadio = radios.first();
      const secondRadio = radios.nth(1);
      await firstRadio.focus();
      await page.keyboard.press('ArrowRight');
      await expect(secondRadio).toBeFocused();
    } else {
      await expect(page.getByRole('button', { name: /continuar con google/i })).toBeVisible();
    }

    await page.setViewportSize({ width: 1280, height: 720 });
    await gotoAndWait(page, '/');
    const primaryNav = page.locator('nav[aria-label="Navegacion principal"]');
    await expect(primaryNav).toBeVisible();
    expect(await primaryNav.locator('a, button').count()).toBeGreaterThan(0);
  });
});

test.describe('Formularios', () => {
  test('inputs, errores, campos requeridos, descripciones y grupos cumplen accesibilidad', async ({
    page,
  }) => {
    await gotoAndWait(page, '/reportes');
    await expectLabelsForInputs(page, 'input, textarea, select');

    const submit = page.locator('button[type="submit"]').first();
    await expect(submit).toBeVisible();
    if (await submit.isEnabled()) {
      await submit.click();
      expect(await page.locator('[role="alert"], [aria-live="assertive"]').count()).toBeGreaterThan(
        0
      );
    } else {
      await expect(submit).toBeDisabled();
    }

    for (const field of await page.locator('[aria-required="true"], [required]').all()) {
      const label = field.locator('xpath=preceding-sibling::label | preceding::label[1]');
      const labelText = (await label.textContent())?.toLowerCase() ?? '';
      expect(labelText.includes('*') || labelText.includes('requerido')).toBe(true);
    }

    await page.waitForTimeout(500);
    for (const field of await page.locator('[aria-describedby*="error"]').all()) {
      const describedbyId = await field.getAttribute('aria-describedby');
      if (describedbyId) {
        await expect(page.locator(`#${describedbyId}`)).toBeVisible();
      }
    }

    const groups = page.locator('[role="group"][aria-labelledby]');
    if ((await groups.count()) > 0) {
      await expect(groups.first()).toBeVisible();
    } else {
      await expect(page.getByRole('button', { name: /continuar con google/i })).toBeVisible();
    }
  });
});

test.describe('Imagenes y encabezados', () => {
  test('imagenes tienen alt adecuado y encabezados estructura correcta', async ({ page }) => {
    await gotoAndWait(page, '/');

    for (const img of await page.locator('img').all()) {
      const alt = await img.getAttribute('alt');
      const role = await img.getAttribute('role');
      expect(alt !== null || role === 'presentation' || role === 'none').toBe(true);
    }

    for (const img of await page.locator('img:not([role="presentation"]):not([alt=""])').all()) {
      const alt = await img.getAttribute('alt');
      if (alt) {
        expect(alt.length).toBeGreaterThan(2);
        expect(alt.toLowerCase()).not.toMatch(/^(imagen?|image|foto|photo|picture)$/);
      }
    }

    expect(await page.locator('h1').count()).toBe(1);

    let previousLevel = 0;
    const violations: string[] = [];
    for (const heading of await page.locator('h1, h2, h3, h4, h5, h6').all()) {
      const tagName = await heading.evaluate((el) => el.tagName.toLowerCase());
      const currentLevel = Number.parseInt(tagName.slice(1), 10);
      const text = await heading.textContent();
      if (currentLevel > previousLevel + 1) {
        violations.push(`Salto de h${previousLevel} a h${currentLevel}: ${text ?? ''}`);
      }
      previousLevel = currentLevel;
    }

    expect(violations).toHaveLength(0);
  });
});

test.describe('Landmarks y tablas', () => {
  test('landmarks y tablas usan semantica adecuada', async ({ page }) => {
    await gotoAndWait(page, '/');
    expect(await page.locator('main, [role="main"]').count()).toBeGreaterThanOrEqual(1);
    expect(await page.locator('nav, [role="navigation"]').count()).toBeGreaterThanOrEqual(1);
    expect(await page.locator('header, [role="banner"]').count()).toBeGreaterThanOrEqual(1);
    await expect(page.locator('footer[role="contentinfo"], [role="contentinfo"]')).toBeVisible();

    const navs = await page.locator('nav, [role="navigation"]').all();
    if (navs.length > 1) {
      const labels = new Set<string>();
      for (const nav of navs) {
        const ariaLabel = await nav.getAttribute('aria-label');
        const ariaLabelledby = await nav.getAttribute('aria-labelledby');
        if (ariaLabel) {
          expect(labels.has(ariaLabel)).toBe(false);
          labels.add(ariaLabel);
        } else if (ariaLabelledby) {
          const labelText = await page.locator(`#${ariaLabelledby}`).textContent();
          if (labelText) {
            expect(labels.has(labelText)).toBe(false);
            labels.add(labelText);
          }
        }
      }
    }

    await gotoAndWait(page, '/dashboard');
    for (const table of await page.locator('table').all()) {
      const caption = await table.locator('caption').count();
      const ariaLabelledby = await table.getAttribute('aria-labelledby');
      const ariaLabel = await table.getAttribute('aria-label');
      expect(Boolean(caption > 0 || ariaLabelledby || ariaLabel)).toBe(true);
    }

    for (const th of await page.locator('th').all()) {
      const scope = await th.getAttribute('scope');
      expect(scope === 'col' || scope === 'row' || scope === null).toBe(true);
    }
  });
});

test.describe('Carga, contraste y responsive', () => {
  test('loading, live regions, contraste, zoom y touch targets son accesibles', async ({
    page,
  }) => {
    await gotoAndWait(page, '/dashboard');
    const loadingCount = await page.locator('[aria-busy="true"]').count();
    const loadedCount = await page.locator('[aria-busy="false"]').count();
    expect(loadingCount > 0 || loadedCount > 0).toBe(true);

    const liveRegions = await page.locator('[aria-live]').all();
    expect(liveRegions.length).toBeGreaterThan(0);
    for (const region of liveRegions) {
      const ariaAtomic = await region.getAttribute('aria-atomic');
      expect(ariaAtomic === 'true' || ariaAtomic === null).toBe(true);
    }

    await gotoAndWait(page, '/');
    expect(
      (await new AxeBuilder({ page }).withRules(['color-contrast']).analyze()).violations
    ).toHaveLength(0);

    await page.evaluate(() => {
      document.body.style.zoom = '2';
    });
    const hasHorizontalScroll = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(hasHorizontalScroll).toBe(false);

    await page.setViewportSize({ width: 375, height: 667 });
    await gotoAndWait(page, '/');
    for (const button of (await page.locator('button, a.mantine-Button-root').all()).slice(0, 10)) {
      const box = await button.boundingBox();
      if (box) {
        expect(box.height).toBeGreaterThanOrEqual(40);
        expect(box.width).toBeGreaterThanOrEqual(40);
      }
    }
  });
});

test.describe('Mapa, modo oscuro, movimiento y filtros', () => {
  test('mapa, modo oscuro, reduced motion, filtros y paginacion exponen ayudas accesibles', async ({
    page,
  }) => {
    await gotoAndWait(page, '/mapa');
    const textAlternative = page.locator(
      '[aria-label*="descripcion"], [aria-label*="textual"], button:has-text("descripcion")'
    );
    const mapDescription = page.locator('[role="application"][aria-label*="mapa"]');
    expect((await textAlternative.count()) > 0 || (await mapDescription.count()) > 0).toBe(true);

    await page.waitForSelector('.maplibregl-map');
    await expect(page.locator('.maplibregl-ctrl-zoom-in')).toHaveAttribute('aria-label', /.+/);
    await expect(page.locator('.maplibregl-ctrl-zoom-out')).toHaveAttribute('aria-label', /.+/);

    await gotoAndWait(page, '/reportes');
    const manualCoordinates = page.getByRole('button', { name: /coordenadas manualmente/i });
    if ((await manualCoordinates.count()) > 0) {
      await expect(manualCoordinates).toBeVisible();
    } else {
      await expect(page.getByRole('button', { name: /continuar con google/i })).toBeVisible();
    }

    await gotoAndWait(page, '/');
    await page.getByRole('button', { name: /modo oscuro/i }).click();
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', 'dark');
    expect(
      (await new AxeBuilder({ page }).withRules(['color-contrast']).analyze()).violations
    ).toHaveLength(0);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    await gotoAndWait(page, '/');
    for (const element of (await page.locator('[class*="animate"]').all()).slice(0, 5)) {
      const animationDuration = await element.evaluate(
        (el) => window.getComputedStyle(el).animationDuration
      );
      expect(Number.parseFloat(animationDuration)).toBeLessThanOrEqual(0.01);
    }

    await gotoAndWait(page, '/admin/reports');
    await expectLabelsForInputs(page, 'input[type="text"], select');
    expect(await page.locator('[aria-live="polite"]').count()).toBeGreaterThan(0);

    const pagination = page.locator('[aria-label*="paginacion"], [aria-label*="Pagination"]');
    if ((await pagination.count()) > 0) {
      await expectVisibleIfAny(page.locator('[aria-label*="siguiente"], [aria-label*="next"]'));
      await expectVisibleIfAny(page.locator('[aria-label*="anterior"], [aria-label*="previous"]'));
    }
  });
});
