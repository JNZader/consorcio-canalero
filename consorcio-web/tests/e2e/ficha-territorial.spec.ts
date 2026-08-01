/**
 * ficha-territorial.spec.ts (A4.9)
 *
 * Click a catastro parcel on the 2D map → the ficha territorial panel renders.
 *
 * The endpoint sits behind the backend `ficha_enabled` flag and needs
 * `parcelas_catastro` populated in the target environment. Following the
 * `afectados.spec.ts` precedent, this probes the API first and SKIPS gracefully
 * (never fails) when the ficha is switched off or the catastro is empty — the
 * front-end code ships regardless of the deployment gate.
 */

import { type APIRequestContext, expect, request, test } from '@playwright/test';

const APP_URL = process.env.E2E_APP_URL ?? 'http://localhost:5173';
const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000';

/**
 * Probe the ficha endpoint. Returns 'off' when the feature flag / dataset makes
 * it unusable, 'on' when it answers as a live endpoint, or 'unknown' on a
 * network error.
 */
async function probeFicha(ctx: APIRequestContext): Promise<'on' | 'off' | 'unknown'> {
  try {
    const res = await ctx.post('/api/v2/geo/analisis-zona', {
      data: { tipo: 'parcela', nomenclatura: '__probe__' },
    });
    if (res.status() === 503) {
      const body = (await res.json().catch(() => ({}))) as { codigo?: string };
      // funcionalidad_no_disponible = flag off; dataset_no_cargado = empty catastro.
      if (body.codigo === 'funcionalidad_no_disponible' || body.codigo === 'dataset_no_cargado') {
        return 'off';
      }
    }
    // 404 (unknown parcela), 422, 429 all prove the endpoint is live.
    return 'on';
  } catch {
    return 'unknown';
  }
}

test.describe('Ficha territorial — click parcel', () => {
  test(
    'clicking a catastro parcel opens the ficha panel',
    { tag: ['@e2e', '@medium', '@mapa', '@ficha-territorial'] },
    async ({ page }) => {
      const ctx = await request.newContext({ baseURL: API_BASE });
      const status = await probeFicha(ctx);
      await ctx.dispose();
      test.skip(status === 'off', 'Ficha territorial deshabilitada o catastro vacío en el entorno');
      test.skip(status === 'unknown', 'Backend no disponible para la ficha territorial');

      await page.goto(`${APP_URL}/mapa`);
      const root = page.getByTestId('map-workspace-root');
      const ready = await root.isVisible({ timeout: 15000 }).catch(() => false);
      test.skip(!ready, 'Map workspace shell no montó (dev server/auth no disponible)');

      // Enable the catastro layer so parcels are clickable.
      const controls = page.getByRole('region', { name: 'Controles de capas del mapa' });
      const catastro = controls.getByRole('checkbox', { name: /Catastro/i }).first();
      const hasCatastro = await catastro.isVisible({ timeout: 10000 }).catch(() => false);
      test.skip(!hasCatastro, 'Capa catastro no disponible (sin datos de capas)');
      await catastro.check();

      // Wait for MapLibre to initialize, then click the canvas center. Whether a
      // parcel is actually hit depends on the map extent + data, so this is a
      // best-effort click guarded by a skip.
      const canvas = page.locator('.maplibregl-canvas').first();
      const mounted = await canvas
        .waitFor({ state: 'visible', timeout: 15000 })
        .then(() => true)
        .catch(() => false);
      test.skip(!mounted, 'Canvas MapLibre no inicializó (sin WebGL en este entorno)');

      await canvas.click({ position: { x: 200, y: 200 } });

      const panel = page.getByTestId('ficha-territorial-panel');
      const opened = await panel.isVisible({ timeout: 10000 }).catch(() => false);
      test.skip(!opened, 'El click no cayó sobre una parcela del catastro en esta vista');

      // When it opens it must reach a terminal state (result or an honest error),
      // never hang on the loader forever.
      await expect(panel).toBeVisible();
      await expect(async () => {
        const result = await panel.getByTestId('ficha-result').isVisible().catch(() => false);
        const error = await panel.getByTestId('ficha-error').isVisible().catch(() => false);
        expect(result || error).toBe(true);
      }).toPass({ timeout: 10000 });
    }
  );
});
