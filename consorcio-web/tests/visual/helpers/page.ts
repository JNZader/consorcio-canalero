import { expect, type Page } from '@playwright/test';
import { installNetworkStubs } from './network';

export type ColorSchemeName = 'light' | 'dark';

export interface ViewportSize {
  width: number;
  height: number;
}

const STABLE_CSS = `
  *, *::before, *::after {
    animation-duration: 0s !important;
    animation-delay: 0s !important;
    transition-duration: 0s !important;
    transition-delay: 0s !important;
    scroll-behavior: auto !important;
    caret-color: transparent !important;
  }

  /*
   * En Actions el stack de enlaces del footer medía ~63px más que en la
   * misma imagen corrida a mano: el gap dejaba de ser 8px y "Argentina"
   * se separaba de "Mapa". Estas reglas fijan ese stack para que las dos
   * corridas midan el mismo alto, sin cambiar el componente.
   */
  footer nav .mantine-Stack-root {
    gap: 8px !important;
    height: auto !important;
    min-height: 0 !important;
    justify-content: flex-start !important;
  }
  footer nav a {
    margin: 0 !important;
  }
`;

/**
 * Tema, movimiento y red antes de la primera navegación.
 * El año del footer se enmascara en la captura: no se congela `Date`,
 * porque varios timeouts del mapa miden `Date.now()`.
 */
export async function installDeterminism(page: Page, theme: ColorSchemeName): Promise<void> {
  await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
  await page.addInitScript(
    ({ scheme, css }) => {
      try {
        localStorage.setItem('mantine-color-scheme-value', scheme);
      } catch {
        // Si el storage está bloqueado, `prefers-color-scheme` sigue el emulateMedia.
      }
      const root = document.documentElement;
      if (!root) return;
      root.setAttribute('data-mantine-color-scheme', scheme);
      root.style.colorScheme = scheme;
      const style = document.createElement('style');
      style.setAttribute('data-visual-regression', 'true');
      style.textContent = css;
      root.appendChild(style);
    },
    { scheme: theme, css: STABLE_CSS }
  );
  await installNetworkStubs(page);
}

export async function openStableRoute(
  page: Page,
  path: string,
  theme: ColorSchemeName,
  viewport: ViewportSize
): Promise<void> {
  await page.setViewportSize(viewport);
  await installDeterminism(page, theme);
  await page.goto(path, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.locator('#main-content').waitFor({ state: 'attached' });

  const themeLabel = theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro';
  await expect(page.getByRole('button', { name: themeLabel })).toBeVisible();

  if (viewport.width >= 768) {
    await expect(page.getByRole('link', { name: 'Iniciar Sesión' }).first()).toBeVisible();
  }

  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => resolve());
        });
      })
  );
}

/** Regiones que cambian solas: canvas del mapa, teselas y el año del footer. */
export function dynamicMasks(page: Page) {
  return [
    page.locator('canvas'),
    page.locator('.maplibregl-map'),
    page.locator('footer').getByText(/©/),
    page.locator('time'),
  ];
}
