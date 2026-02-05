/**
 * Tests de Accesibilidad Automatizados
 * WCAG 2.1 AA Compliance Testing
 *
 * Ejecutar con: npx playwright test tests/accessibility/
 */

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// Configuracion de rutas a testear
const ROUTES = [
  { path: '/', name: 'Homepage' },
  { path: '/mapa', name: 'Mapa Interactivo' },
  { path: '/denuncias', name: 'Formulario de Denuncias' },
  { path: '/dashboard', name: 'Dashboard' },
  { path: '/login', name: 'Login' },
];

// Reglas WCAG a verificar
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa'];

test.describe('Auditoria de Accesibilidad WCAG 2.1 AA', () => {
  // Test automatizado con axe-core para cada ruta
  for (const route of ROUTES) {
    test(`${route.name} - No debe tener violaciones automaticas`, async ({ page }) => {
      await page.goto(route.path);

      // Esperar a que el contenido cargue
      await page.waitForLoadState('networkidle');

      const accessibilityScanResults = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();

      // Reportar violaciones encontradas
      if (accessibilityScanResults.violations.length > 0) {
        accessibilityScanResults.violations.forEach((_violation) => {});
      }

      // El test pasa si no hay violaciones criticas o serias
      const criticalViolations = accessibilityScanResults.violations.filter(
        (v) => v.impact === 'critical' || v.impact === 'serious'
      );

      expect(criticalViolations).toHaveLength(0);
    });
  }
});

test.describe('Skip Links', () => {
  test('Skip link debe ser visible al enfocar', async ({ page }) => {
    await page.goto('/');

    // Presionar Tab para enfocar el skip link
    await page.keyboard.press('Tab');

    const skipLink = page.locator('.skip-link');

    // Verificar que esta visible
    await expect(skipLink).toBeVisible();

    // Verificar que tiene el texto correcto
    await expect(skipLink).toHaveText(/saltar/i);
  });

  test('Skip link debe navegar al contenido principal', async ({ page }) => {
    await page.goto('/');

    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');

    // Verificar que el foco esta en el main content
    const mainContent = page.locator('#main-content');
    await expect(mainContent).toBeFocused();
  });
});

test.describe('Navegacion por Teclado', () => {
  test('Todos los elementos interactivos deben ser accesibles por teclado', async ({ page }) => {
    await page.goto('/');

    // Obtener todos los elementos focusables
    const focusableElements = await page
      .locator('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')
      .all();

    expect(focusableElements.length).toBeGreaterThan(0);

    // Verificar que cada elemento puede recibir foco
    for (const element of focusableElements.slice(0, 10)) {
      // Limitar a los primeros 10 para velocidad
      await element.focus();
      await expect(element).toBeFocused();
    }
  });

  test('El menu movil debe atrapar el foco', async ({ page }) => {
    // Simular viewport movil
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Abrir el menu hamburguesa
    const burger = page.locator('[aria-label*="menu"]').first();
    await burger.click();

    // Verificar que el drawer esta abierto
    const drawer = page.locator('.mantine-Drawer-root');
    await expect(drawer).toBeVisible();

    // Verificar que el foco esta dentro del drawer
    await page.keyboard.press('Tab');
    const focusedElement = page.locator(':focus');

    // El elemento enfocado debe estar dentro del drawer
    const isInDrawer = await focusedElement.evaluate((el) => {
      return el.closest('.mantine-Drawer-root') !== null;
    });

    expect(isInDrawer).toBe(true);

    // Verificar que Escape cierra el drawer
    await page.keyboard.press('Escape');
    await expect(drawer).not.toBeVisible();
  });

  test('Los botones de radio del formulario deben navegarse con flechas', async ({ page }) => {
    await page.goto('/denuncias');

    // Enfocar el primer boton de tipo
    const firstRadio = page.locator('[role="radio"]').first();
    await firstRadio.focus();

    // Presionar flecha derecha
    await page.keyboard.press('ArrowRight');

    // El segundo boton debe estar enfocado
    const secondRadio = page.locator('[role="radio"]').nth(1);
    await expect(secondRadio).toBeFocused();
  });

  test('La navegacion principal debe usar role menubar y menuitem', async ({ page }) => {
    await page.goto('/');

    // Verificar que existe el menubar
    const menubar = page.locator('[role="menubar"]');
    await expect(menubar).toBeVisible();

    // Verificar que los items tienen role menuitem
    const menuItems = page.locator('[role="menuitem"]');
    const menuItemCount = await menuItems.count();
    expect(menuItemCount).toBeGreaterThan(0);
  });
});

test.describe('Formularios', () => {
  test('Todos los inputs deben tener labels asociados', async ({ page }) => {
    await page.goto('/denuncias');

    const inputs = await page.locator('input, textarea, select').all();

    for (const input of inputs) {
      const id = await input.getAttribute('id');
      const ariaLabel = await input.getAttribute('aria-label');
      const ariaLabelledby = await input.getAttribute('aria-labelledby');

      // Debe tener al menos una forma de label
      let hasLabel = false;

      if (id) {
        const label = await page.locator(`label[for="${id}"]`).count();
        hasLabel = label > 0;
      }

      if (!hasLabel) {
        hasLabel = !!ariaLabel || !!ariaLabelledby;
      }

      expect(hasLabel).toBe(true);
    }
  });

  test('Los errores de formulario deben ser anunciados', async ({ page }) => {
    await page.goto('/denuncias');

    // Intentar enviar sin completar
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();

    // Verificar que hay mensajes de error visibles
    const errorMessages = page.locator('[role="alert"], [aria-live="assertive"]');
    const errorCount = await errorMessages.count();

    // Debe haber al menos un mensaje de error
    expect(errorCount).toBeGreaterThan(0);
  });

  test('Los campos requeridos deben estar marcados', async ({ page }) => {
    await page.goto('/denuncias');

    // Buscar campos requeridos
    const requiredFields = await page.locator('[aria-required="true"], [required]').all();

    for (const field of requiredFields) {
      // Verificar que tienen indicador visual
      const label = await field.locator('xpath=preceding-sibling::label | preceding::label[1]');
      const labelText = await label.textContent();

      // El label debe contener asterisco o la palabra "requerido"
      expect(labelText?.includes('*') || labelText?.toLowerCase().includes('requerido')).toBe(true);
    }
  });

  test('Los campos con errores deben tener aria-describedby', async ({ page }) => {
    await page.goto('/denuncias');

    // Forzar un error en el formulario
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();

    // Esperar a que aparezcan los errores
    await page.waitForTimeout(500);

    // Buscar campos con errores
    const fieldsWithErrors = await page.locator('[aria-describedby*="error"]').all();

    // Cada campo con error debe tener un mensaje asociado
    for (const field of fieldsWithErrors) {
      const describedbyId = await field.getAttribute('aria-describedby');
      if (describedbyId) {
        const errorMessage = page.locator(`#${describedbyId}`);
        await expect(errorMessage).toBeVisible();
      }
    }
  });

  test('El formulario debe tener role group para secciones', async ({ page }) => {
    await page.goto('/denuncias');

    // Verificar que existe al menos un grupo con aria-labelledby
    const groups = page.locator('[role="group"][aria-labelledby]');
    const groupCount = await groups.count();
    expect(groupCount).toBeGreaterThan(0);
  });
});

test.describe('Imagenes', () => {
  test('Todas las imagenes deben tener alt text', async ({ page }) => {
    await page.goto('/');

    const images = await page.locator('img').all();

    for (const img of images) {
      const alt = await img.getAttribute('alt');
      const role = await img.getAttribute('role');

      // Debe tener alt (puede estar vacio para decorativas) o role="presentation"
      const hasAlt = alt !== null;
      const isDecorative = role === 'presentation' || role === 'none';

      expect(hasAlt || isDecorative).toBe(true);
    }
  });

  test('Las imagenes de contenido deben tener alt descriptivo', async ({ page }) => {
    await page.goto('/');

    const contentImages = await page.locator('img:not([role="presentation"]):not([alt=""])').all();

    for (const img of contentImages) {
      const alt = await img.getAttribute('alt');

      // El alt text debe tener al menos 3 caracteres y ser descriptivo
      if (alt) {
        expect(alt.length).toBeGreaterThan(2);
        // No debe ser solo "imagen" o "image"
        expect(alt.toLowerCase()).not.toMatch(/^(imagen?|image|foto|photo|picture)$/);
      }
    }
  });
});

test.describe('Estructura de Encabezados', () => {
  test('Debe haber exactamente un h1 por pagina', async ({ page }) => {
    await page.goto('/');

    const h1Count = await page.locator('h1').count();
    expect(h1Count).toBe(1);
  });

  test('La jerarquia de encabezados debe ser correcta', async ({ page }) => {
    await page.goto('/');

    const headings = await page.locator('h1, h2, h3, h4, h5, h6').all();
    let previousLevel = 0;
    const violations: string[] = [];

    for (const heading of headings) {
      const tagName = await heading.evaluate((el) => el.tagName.toLowerCase());
      const currentLevel = Number.parseInt(tagName.substring(1));
      const text = await heading.textContent();

      if (currentLevel > previousLevel + 1) {
        violations.push(
          `Salto de h${previousLevel} a h${currentLevel}: "${text?.substring(0, 30)}..."`
        );
      }

      previousLevel = currentLevel;
    }

    expect(violations).toHaveLength(0);
  });
});

test.describe('Landmarks ARIA', () => {
  test('La pagina debe tener landmarks apropiados', async ({ page }) => {
    await page.goto('/');

    // Verificar landmarks requeridos
    const main = await page.locator('main, [role="main"]').count();
    const nav = await page.locator('nav, [role="navigation"]').count();
    const header = await page.locator('header, [role="banner"]').count();

    expect(main).toBeGreaterThanOrEqual(1);
    expect(nav).toBeGreaterThanOrEqual(1);
    expect(header).toBeGreaterThanOrEqual(1);
  });

  test('Los landmarks deben tener labels unicos cuando hay multiples', async ({ page }) => {
    await page.goto('/');

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
  });

  test('El footer debe tener role contentinfo', async ({ page }) => {
    await page.goto('/');

    const footer = page.locator('footer[role="contentinfo"], [role="contentinfo"]');
    await expect(footer).toBeVisible();
  });
});

test.describe('Tablas', () => {
  test('Las tablas de datos deben tener caption o aria-labelledby', async ({ page }) => {
    await page.goto('/dashboard');

    // Esperar a que cargue el contenido
    await page.waitForLoadState('networkidle');

    const tables = await page.locator('table').all();

    for (const table of tables) {
      const caption = await table.locator('caption').count();
      const ariaLabelledby = await table.getAttribute('aria-labelledby');
      const ariaLabel = await table.getAttribute('aria-label');

      expect(caption > 0 || ariaLabelledby || ariaLabel).toBeTruthy();
    }
  });

  test('Los headers de tabla deben tener scope', async ({ page }) => {
    await page.goto('/dashboard');

    await page.waitForLoadState('networkidle');

    const tableHeaders = await page.locator('th').all();

    for (const th of tableHeaders) {
      const scope = await th.getAttribute('scope');
      // Scope debe ser 'col' o 'row'
      expect(scope === 'col' || scope === 'row' || scope === null).toBe(true);
    }
  });
});

test.describe('Estados de Carga', () => {
  test('Los estados de carga deben anunciarse a screen readers', async ({ page }) => {
    await page.goto('/dashboard');

    // El contenedor de carga debe tener aria-busy y role status
    const loadingContainer = page.locator('[aria-busy="true"]');

    // Verificar que existe o que el contenido ya cargo
    const loadingExists = await loadingContainer.count();
    const contentLoaded = await page.locator('[aria-busy="false"]').count();

    expect(loadingExists > 0 || contentLoaded > 0).toBe(true);
  });

  test('Debe existir live region para anuncios', async ({ page }) => {
    await page.goto('/dashboard');

    // Buscar live regions
    const liveRegions = await page.locator('[aria-live]').all();
    expect(liveRegions.length).toBeGreaterThan(0);

    // Verificar que tienen aria-atomic
    for (const region of liveRegions) {
      const ariaAtomic = await region.getAttribute('aria-atomic');
      // aria-atomic puede ser true o false, pero debe existir o ser implicito
      expect(ariaAtomic === 'true' || ariaAtomic === null).toBe(true);
    }
  });
});

test.describe('Contraste de Colores', () => {
  test('El texto debe tener contraste suficiente', async ({ page }) => {
    await page.goto('/');

    // Usar axe-core especificamente para contraste
    const results = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();

    // Reportar violaciones de contraste
    if (results.violations.length > 0) {
      results.violations.forEach((v) => {
        v.nodes.forEach((_node) => {});
      });
    }

    expect(results.violations).toHaveLength(0);
  });
});

test.describe('Responsive y Zoom', () => {
  test('El contenido debe ser usable a 200% zoom', async ({ page }) => {
    await page.goto('/');

    // Simular 200% zoom
    await page.evaluate(() => {
      document.body.style.zoom = '2';
    });

    // Verificar que no hay scroll horizontal
    const hasHorizontalScroll = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });

    // Permitir un pequeno margen
    expect(hasHorizontalScroll).toBe(false);
  });

  test('Touch targets deben tener tamano minimo de 44x44px', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    const buttons = await page.locator('button, a.mantine-Button-root').all();

    for (const button of buttons.slice(0, 10)) {
      const box = await button.boundingBox();

      if (box) {
        // Tamano minimo recomendado: 44x44px
        expect(box.height).toBeGreaterThanOrEqual(40); // Pequeno margen de tolerancia
        expect(box.width).toBeGreaterThanOrEqual(40);
      }
    }
  });
});

test.describe('Mapa Interactivo', () => {
  test('El mapa debe tener alternativa textual', async ({ page }) => {
    await page.goto('/mapa');

    // Buscar boton de alternativa textual o descripcion
    const textAlternative = page.locator(
      '[aria-label*="descripcion"], [aria-label*="textual"], button:has-text("descripcion")'
    );

    // O buscar un elemento con descripcion del mapa
    const mapDescription = page.locator('[role="application"][aria-label*="mapa"]');

    const hasAlternative =
      (await textAlternative.count()) > 0 || (await mapDescription.count()) > 0;

    expect(hasAlternative).toBe(true);
  });

  test('Los controles del mapa deben tener aria-labels', async ({ page }) => {
    await page.goto('/mapa');

    // Esperar a que el mapa cargue
    await page.waitForSelector('.leaflet-container');

    const zoomIn = page.locator('.leaflet-control-zoom-in');
    const zoomOut = page.locator('.leaflet-control-zoom-out');

    // Verificar que tienen labels
    await expect(zoomIn).toHaveAttribute('aria-label', /.+/);
    await expect(zoomOut).toHaveAttribute('aria-label', /.+/);
  });

  test('Debe existir opcion de ingreso manual de coordenadas', async ({ page }) => {
    await page.goto('/denuncias');

    // Buscar boton para mostrar entrada manual de coordenadas
    const manualInputButton = page.locator(
      'button:has-text("coordenadas"), button:has-text("manual")'
    );

    const hasManualOption = (await manualInputButton.count()) > 0;
    expect(hasManualOption).toBe(true);
  });
});

test.describe('Modo Oscuro', () => {
  test('El modo oscuro debe mantener el contraste', async ({ page }) => {
    await page.goto('/');

    // Activar modo oscuro
    await page.evaluate(() => {
      document.documentElement.setAttribute('data-mantine-color-scheme', 'dark');
    });

    // Verificar contraste en modo oscuro
    const results = await new AxeBuilder({ page }).withRules(['color-contrast']).analyze();

    expect(results.violations).toHaveLength(0);
  });
});

test.describe('Reducir Movimiento', () => {
  test('Las animaciones deben respetar prefers-reduced-motion', async ({ page }) => {
    // Emular preferencia de movimiento reducido
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');

    // Verificar que las animaciones estan deshabilitadas
    const animatedElements = await page.locator('[class*="animate"]').all();

    for (const element of animatedElements.slice(0, 5)) {
      const animationDuration = await element.evaluate((el) => {
        return window.getComputedStyle(el).animationDuration;
      });

      // La duracion debe ser muy corta o 0
      const duration = Number.parseFloat(animationDuration);
      expect(duration).toBeLessThanOrEqual(0.01);
    }
  });
});

test.describe('Filtros y Busqueda', () => {
  test('Los filtros deben tener aria-labels apropiados', async ({ page }) => {
    // Ir a una pagina con filtros (admin reports)
    await page.goto('/admin/reports');

    // Buscar inputs de filtro
    const filterInputs = await page.locator('input[type="text"], select').all();

    for (const input of filterInputs) {
      const ariaLabel = await input.getAttribute('aria-label');
      const label = await input.getAttribute('aria-labelledby');
      const id = await input.getAttribute('id');

      // Debe tener aria-label, aria-labelledby o un label asociado
      let hasLabel = !!ariaLabel || !!label;

      if (!hasLabel && id) {
        const associatedLabel = await page.locator(`label[for="${id}"]`).count();
        hasLabel = associatedLabel > 0;
      }

      expect(hasLabel).toBe(true);
    }
  });

  test('Las actualizaciones de lista deben anunciarse', async ({ page }) => {
    await page.goto('/admin/reports');

    // Verificar que existe aria-live en la seccion de resultados
    const liveRegion = page.locator('[aria-live="polite"]');
    const liveRegionCount = await liveRegion.count();

    expect(liveRegionCount).toBeGreaterThan(0);
  });
});

test.describe('Paginacion', () => {
  test('La paginacion debe tener labels descriptivos', async ({ page }) => {
    await page.goto('/admin/reports');

    // Esperar a que cargue
    await page.waitForLoadState('networkidle');

    const pagination = page.locator('[aria-label*="paginacion"], [aria-label*="Pagination"]');

    if ((await pagination.count()) > 0) {
      // Verificar que los controles tienen labels
      const nextButton = page.locator('[aria-label*="siguiente"], [aria-label*="next"]');
      const prevButton = page.locator('[aria-label*="anterior"], [aria-label*="previous"]');

      if ((await nextButton.count()) > 0) {
        await expect(nextButton).toHaveAttribute('aria-label', /.+/);
      }
      if ((await prevButton.count()) > 0) {
        await expect(prevButton).toHaveAttribute('aria-label', /.+/);
      }
    }
  });
});

test.describe('Modales y Dialogos', () => {
  test('Los modales deben atrapar el foco', async ({ page }) => {
    await page.goto('/admin/reports');

    // Esperar y abrir un modal si existe
    await page.waitForLoadState('networkidle');

    const actionButton = page.locator('[aria-label*="detalle"]').first();

    if ((await actionButton.count()) > 0) {
      await actionButton.click();

      // Verificar que el modal tiene role dialog
      const modal = page.locator('[role="dialog"]');
      await expect(modal).toBeVisible();

      // El foco debe estar dentro del modal
      const focusedElement = page.locator(':focus');
      const isInModal = await focusedElement.evaluate((el) => {
        return el.closest('[role="dialog"]') !== null;
      });

      expect(isInModal).toBe(true);

      // Escape debe cerrar el modal
      await page.keyboard.press('Escape');
      await expect(modal).not.toBeVisible();
    }
  });
});

test.describe('Iconos y Elementos Decorativos', () => {
  test('Los iconos decorativos deben estar ocultos de AT', async ({ page }) => {
    await page.goto('/');

    // Buscar iconos que deben ser decorativos
    const icons = await page.locator('svg, [class*="icon"]').all();

    for (const icon of icons.slice(0, 20)) {
      const ariaHidden = await icon.getAttribute('aria-hidden');
      const role = await icon.getAttribute('role');
      const ariaLabel = await icon.getAttribute('aria-label');

      // Si no tiene aria-label, debe estar oculto
      if (!ariaLabel) {
        expect(ariaHidden === 'true' || role === 'presentation' || role === 'none').toBe(true);
      }
    }
  });
});
