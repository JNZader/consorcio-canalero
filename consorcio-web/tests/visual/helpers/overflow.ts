import { expect, type Page } from '@playwright/test';

/**
 * El documento no se desplaza de costado. Un píxel de margen cubre el
 * redondeo de bordes fraccionarios; más que eso es overflow horizontal.
 */
export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const metrics = await page.evaluate(() => {
    const root = document.documentElement;
    const body = document.body;
    return {
      viewport: window.innerWidth,
      documentOverflowPx: root.scrollWidth - root.clientWidth,
      bodyOverflowPx: body.scrollWidth - body.clientWidth,
      scrollWidth: root.scrollWidth,
      clientWidth: root.clientWidth,
    };
  });

  expect(
    metrics.documentOverflowPx,
    `overflow horizontal en documentElement (${metrics.scrollWidth}px de scroll en un viewport de ${metrics.viewport}px, client ${metrics.clientWidth}px)`
  ).toBeLessThanOrEqual(1);
  expect(
    metrics.bodyOverflowPx,
    `overflow horizontal en body (${metrics.bodyOverflowPx}px)`
  ).toBeLessThanOrEqual(1);
}
