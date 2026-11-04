import type { Page } from '@playwright/test';

interface Point {
  x: number;
  y: number;
}

/**
 * Gesto táctil de un dedo. Las coordenadas son CSS pixels del viewport,
 * que es lo que espera `Input.dispatchTouchEvent`.
 */
export async function touchSwipe(page: Page, from: Point, to: Point): Promise<void> {
  const client = await page.context().newCDPSession(page);
  const steps = 10;
  const point = (x: number, y: number) => [{ x: Math.round(x), y: Math.round(y), id: 1 }];

  await client.send('Input.dispatchTouchEvent', {
    type: 'touchStart',
    touchPoints: point(from.x, from.y),
  });
  for (let step = 1; step <= steps; step += 1) {
    const x = from.x + ((to.x - from.x) * step) / steps;
    const y = from.y + ((to.y - from.y) * step) / steps;
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: point(x, y),
    });
  }
  await client.send('Input.dispatchTouchEvent', {
    type: 'touchEnd',
    touchPoints: [],
  });
  await client.detach();
}
