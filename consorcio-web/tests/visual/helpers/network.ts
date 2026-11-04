import type { Page, Route } from '@playwright/test';

/** Puerto del `webServer` de playwright.config.ts. Mantenerlos iguales. */
export const VISUAL_DEV_PORT = '5175';

/**
 * PNG de 1×1 gris. Las teselas satelitales y de calles se dibujan en el
 * canvas, que la captura enmascara; el cuerpo fijo evita que el mapa
 * reintente contra Esri, Martin o Earth Engine.
 */
const SOLID_PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
);

const TINY_LINE = {
  type: 'Feature',
  properties: { id: 'demo-1', nombre: 'Tramo demo', longitud_m: 2000 },
  geometry: {
    type: 'LineString',
    coordinates: [
      [-62.54, -32.545],
      [-62.53, -32.544],
    ],
  },
};

const CAMINOS_ENVELOPE = {
  status: 'available',
  projection: 'caminos',
  reason: null,
  data: {
    type: 'FeatureCollection',
    features: [TINY_LINE],
    metadata: { total_tramos: 1, total_consorcios: 1, total_km: 1280 },
    consorcios: [
      {
        nombre: 'Consorcio demo',
        codigo: 'DEMO',
        color: '#2d8f68',
        tramos: 1,
        longitud_km: 1280,
      },
    ],
  },
};

const ZONA_ENVELOPE = {
  status: 'available',
  projection: 'zona',
  reason: null,
  data: {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { nombre: 'Zona demo' },
        geometry: {
          type: 'Polygon',
          coordinates: [
            [
              [-62.79, -32.7],
              [-62.29, -32.7],
              [-62.29, -32.39],
              [-62.79, -32.39],
              [-62.79, -32.7],
            ],
          ],
        },
      },
    ],
  },
};

const CANALES_PUBLICO = {
  relevados: { type: 'FeatureCollection', features: [TINY_LINE] },
  propuestas: { type: 'FeatureCollection', features: [] },
};

const BRANDING = {
  consorcio_area_ha: 88484,
  consorcio_km_caminos: 753,
  map: {
    center: { lat: -32.545, lng: -62.54 },
    zoom: 11,
    bounds: { north: -32.39, south: -32.7, east: -62.29, west: -62.79 },
  },
  cuencas: [
    { id: 'candil', nombre: 'Candil', ha: 18800, color: '#3b82f6' },
    { id: 'ml', nombre: 'ML', ha: 18900, color: '#14b8a6' },
    { id: 'noroeste', nombre: 'Noroeste', ha: 18500, color: '#f97316' },
    { id: 'norte', nombre: 'Norte', ha: 18300, color: '#8b5cf6' },
  ],
  analysis: { default_max_cloud: 20, default_days_back: 30 },
};

function isDevServer(url: URL): boolean {
  const host = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
  return host && url.port === VISUAL_DEV_PORT;
}

function json(body: unknown) {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  };
}

function stubBody(url: URL): { status: number; contentType: string; body: string | Buffer } {
  const path = url.pathname;

  if (path.includes('/public/map/gee/caminos')) {
    return json(CAMINOS_ENVELOPE);
  }
  if (path.includes('/public/map/gee/zona')) {
    return json(ZONA_ENVELOPE);
  }
  if (path.includes('/geo/canales/publico')) {
    return json(CANALES_PUBLICO);
  }
  if (path.includes('/public/settings/branding')) {
    return json(BRANDING);
  }
  if (path.includes('/version.json')) {
    return json({ sha: 'visual-baseline', buildTime: '2026-06-15T15:00:00.000Z' });
  }
  if (path.includes('/geo/layers')) {
    return json({ items: [], total: 0 });
  }

  const lower = path.toLowerCase();
  if (
    lower.endsWith('.png') ||
    lower.endsWith('.jpg') ||
    lower.endsWith('.jpeg') ||
    lower.endsWith('.webp') ||
    lower.endsWith('.gif') ||
    path.includes('/tile/') ||
    path.includes('/tiles/') ||
    path.includes('/MapServer/')
  ) {
    return { status: 200, contentType: 'image/png', body: SOLID_PNG };
  }
  if (lower.endsWith('.pbf') || lower.endsWith('.mvt')) {
    return { status: 200, contentType: 'application/x-protobuf', body: Buffer.alloc(0) };
  }
  if (lower.endsWith('.geojson')) {
    return json({ type: 'FeatureCollection', features: [] });
  }

  return json({ type: 'FeatureCollection', features: [] });
}

async function fulfillStub(route: Route, url: URL): Promise<void> {
  if (route.request().method() === 'OPTIONS') {
    await route.fulfill({
      status: 204,
      headers: corsHeaders(),
      body: '',
    });
    return;
  }
  const stub = stubBody(url);
  await route.fulfill({
    status: stub.status,
    contentType: stub.contentType,
    headers: corsHeaders(),
    body: stub.body,
  });
}

function corsHeaders(): Record<string, string> {
  return {
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    'access-control-allow-headers': '*',
  };
}

/**
 * Deja pasar solo el dev server de Vite (JS, CSS, fuentes self-hosted y
 * GeoJSON de `public/`). Cualquier otro host —API, teselas, glifos, Martin,
 * Sentry— se responde en el proceso y no sale a la red.
 */
export async function installNetworkStubs(page: Page): Promise<void> {
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const sameOriginAsset =
      isDevServer(url) && !url.pathname.startsWith('/api/') && !url.pathname.startsWith('/uploads');

    if (sameOriginAsset) {
      await route.continue();
      return;
    }

    await fulfillStub(route, url);
  });
}
