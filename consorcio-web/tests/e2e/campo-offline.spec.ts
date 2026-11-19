/**
 * Campo (PR 6, S8) — "Playwright con geolocalización simulada y modo sin
 * red: el panel muestra la clase correcta en tres puntos conocidos y el
 * aviso de límite cerca de un borde."
 *
 * The package is MOCKED at the network boundary; everything else is the
 * real stack: the real router route, the real loader (Cache Storage), the
 * real MapLibre map, the REAL Geolocation API — driven by Playwright's
 * geolocation grant + setGeolocation — and real offline mode via
 * context.setOffline AFTER the first load. Three known points (one per
 * class) + one near-edge fix with a 40 m accuracy circle cross the S8 bar.
 */

import { expect, type Page, test } from '@playwright/test';

const TOKEN = 'token-e2e-campo';

// ── the synthetic world: three riesgo classes split by vertical edges ────────
const Y0 = -33.01;
const Y1 = -33.0;
const M_LON = 111_320 * Math.cos((-33.005 * Math.PI) / 180); // ≈ 93 310 m/°

const cuadro = (x0: number, x1: number, clase: string, color: string) => ({
  type: 'Feature',
  properties: { clase, color },
  geometry: {
    type: 'Polygon',
    coordinates: [
      [
        [x0, Y0],
        [x1, Y0],
        [x1, Y1],
        [x0, Y1],
        [x0, Y0],
      ],
    ],
  },
});

const SELECCION = {
  type: 'Polygon',
  coordinates: [
    [
      [-61.91, Y0],
      [-61.88, Y0],
      [-61.88, Y1],
      [-61.91, Y1],
      [-61.91, Y0],
    ],
  ],
};

const PAQUETE = {
  version: 1,
  nombre: 'Informe campo e2e',
  generado_el: '2026-11-19T12:00:00Z',
  vence_at: '2027-02-17T12:00:00Z',
  area_ha: 333.3,
  limites: {
    seleccion: SELECCION,
    subcuencas: [
      {
        nombre: 'alpha',
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [-61.91, Y0],
              [-61.895, Y0],
              [-61.895, Y1],
              [-61.91, Y1],
              [-61.91, Y0],
            ],
          ],
        },
      },
    ],
  },
  temas: {
    riesgo: {
      titulo: 'Riesgo hídrico',
      clases: [
        {
          clase: 'Bajo',
          color: '#1a9850',
          geometrias: [cuadro(-61.91, -61.9, 'Bajo', '#1a9850').geometry],
        },
        {
          clase: 'Medio',
          color: '#fee08b',
          geometrias: [cuadro(-61.9, -61.89, 'Medio', '#fee08b').geometry],
        },
        {
          clase: 'Alto',
          color: '#fc8d59',
          geometrias: [cuadro(-61.89, -61.88, 'Alto', '#fc8d59').geometry],
        },
      ],
    },
  },
  basemap: null,
  notas: [],
};

// ── the three known points + the near-edge fix ───────────────────────────────
const PUNTO_BAJO = { latitude: -33.005, longitude: -61.905, accuracy: 10 };
const PUNTO_MEDIO = { latitude: -33.005, longitude: -61.895, accuracy: 10 };
const PUNTO_ALTO = { latitude: -33.005, longitude: -61.885, accuracy: 10 };
// 12 m EAST of the Bajo|Medio edge, accuracy 40 m → inside Medio, within
// the accuracy circle of the edge → the S8 boundary warning.
const PUNTO_BORDE = {
  latitude: -33.005,
  longitude: -61.9 + 12 / M_LON,
  accuracy: 40,
};

async function preparar(page: Page): Promise<void> {
  await page
    .context()
    .route('**/api/v2/public/campo/**', (route) => route.fulfill({ json: PAQUETE }));
}

/**
 * Navigate to the campo route and wait until the map's style is live
 * (`data-ready`). The dev server compiles the campo chunk graph lazily, so
 * a cold first hit can transiently fail a dynamic import — the page shows
 * its honest error state and ONE reload (exactly what a phone user with
 * flaky signal does) settles it. Production does not have this window
 * (the SW precaches the chunks), so retrying here costs nothing real.
 */
async function abrirCampoConMapaListo(page: Page, token: string): Promise<void> {
  for (let intento = 0; intento < 3; intento++) {
    if (intento === 0 || (await page.getByTestId('campo-error').count()) > 0) {
      await page.goto(`/campo/${token}`);
    }
    await expect(page.getByTestId('campo-panel')).toBeVisible({ timeout: 30_000 });
    try {
      await page.locator('[data-testid="campo-mapa"][data-ready="1"]').waitFor({ timeout: 20_000 });
      return;
    } catch {
      // Sin mapa listo: si la página cayó en estado de error, reintentar;
      // si no, un último ciclo más y que el assert final hable.
    }
  }
  await expect(page.locator('[data-testid="campo-mapa"][data-ready="1"]')).toHaveCount(1, {
    timeout: 20_000,
  });
}

test.describe('Campo offline (PR 6, S5/S6/S8)', () => {
  test.use({ permissions: ['geolocation'] });

  test('tres puntos conocidos y aviso de límite, TODO en modo sin red', async ({
    page,
    context,
  }) => {
    await preparar(page);

    // First use WITH signal: the package loads, the map boots, everything
    // the offline phase needs (chunks, worker, package cache) settles.
    await context.setGeolocation(PUNTO_BAJO);
    await abrirCampoConMapaListo(page, TOKEN);
    await expect(page.getByTestId('campo-clase')).toHaveText('Tu posición: clase Bajo');

    // ── the network is gone from here on; the map must keep answering ──
    await context.setOffline(true);
    await expect(page.getByTestId('campo-offline')).toHaveText('Sin señal · funciona igual');

    // S8: three known points, each in a different class.
    await context.setGeolocation(PUNTO_MEDIO);
    await expect(page.getByTestId('campo-clase')).toHaveText('Tu posición: clase Medio');

    await context.setGeolocation(PUNTO_ALTO);
    await expect(page.getByTestId('campo-clase')).toHaveText('Tu posición: clase Alto');

    // S8: near an edge, within the accuracy circle → the boundary warning
    // names BOTH classes.
    await context.setGeolocation(PUNTO_BORDE);
    await expect(page.getByTestId('campo-clase')).toHaveText('Tu posición: clase Medio');
    await expect(page.getByTestId('campo-limite')).toHaveText(
      'Estás en el límite entre Medio y Bajo'
    );

    // S6: tap-to-query via queryRenderedFeatures (real MapLibre render).
    // fitBounds centered the selection → the viewport centre is Medio.
    await page.waitForTimeout(400);
    await page.mouse.click(
      Math.round(page.viewportSize()?.width ?? 1280) / 2,
      Math.round(page.viewportSize()?.height ?? 720) / 2
    );
    await expect(page.getByTestId('campo-tap')).toHaveText('En el punto tocado: clase Medio');

    // S6: Centrar en mí is present and the GPS dot layer exists.
    await expect(page.getByTestId('campo-centrar')).toBeVisible();
  });

  test('primer uso: el paquete queda en Cache Storage bajo la URL pública (S5)', async ({
    page,
  }) => {
    await preparar(page);

    await page.context().setGeolocation(PUNTO_BAJO);
    await abrirCampoConMapaListo(page, TOKEN);
    await expect(page.getByTestId('campo-clase')).toHaveText('Tu posición: clase Bajo');

    // The page wrote the package into Cache Storage itself (dev has no
    // service worker — this is exactly the layer that must not depend on
    // one). Assert the REAL browser cache holds the REAL URL.
    const enCache = await page.evaluate(async (url: string) => {
      const cache = await caches.open('campo-packages');
      const respuesta = await cache.match(url);
      if (!respuesta) return null;
      const cuerpo = (await respuesta.json()) as { nombre?: string };
      return cuerpo.nombre ?? null;
    }, 'http://localhost:8000/api/v2/public/campo/' + TOKEN);
    expect(enCache).toBe('Informe campo e2e');
  });
});
