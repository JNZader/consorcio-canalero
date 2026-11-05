/**
 * Pages advanced mode. Este archivo vive en `public/` para que Vite lo copie
 * a `dist/_worker.js`, que es el artefacto que Cloudflare publica.
 *
 * `functions/` no alcanzó en este proyecto: el preview sirvió el shell de la
 * SPA (200, `text/html`, cache immutable de `/assets/*`) para un
 * `/assets/*.js` que no existe. El `_worker.js` del output sí corre en cada
 * request.
 *
 * Sin `404.html` de raíz, `env.ASSETS` hace el fallback SPA (rutas sin
 * archivo → index.html 200). Un chunk viejo cae en ese mismo fallback y el
 * navegador intenta evaluar HTML (FE-01). Si la URL es un archivo estático y
 * la respuesta es HTML 200 o un 404 HTML, devolvemos 404 `text/plain`.
 *
 * Una ruta HTML que la app no tiene registrada también llegaba como 200 con
 * el shell (soft-404). Esa se devuelve con el mismo HTML y status 404, para
 * que el cliente pinte Not Found y un crawler vea el código real.
 */

const STATIC_ASSET =
  /\.(?:js|mjs|css|map|json|webmanifest|txt|xml|ico|png|jpe?g|gif|svg|webp|avif|woff2?|ttf|otf|eot|wasm|pmtiles|geojson)$/i;

export function isStaticAssetPath(pathname) {
  return STATIC_ASSET.test(pathname);
}

/**
 * @param {string} pathname
 * @param {number} status
 * @param {string | null | undefined} contentType
 */
export function shouldReplaceWithPlain404(pathname, status, contentType) {
  if (!isStaticAssetPath(pathname)) return false;
  if (status === 404) return true;
  const type = (contentType || '').toLowerCase();
  return status === 200 && type.includes('text/html');
}

export function plainNotFound() {
  return new Response('Not found\n', {
    status: 404,
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store',
      'x-content-type-options': 'nosniff',
    },
  });
}

/**
 * Rutas que el router de la SPA conoce. Una URL que no está acá y que el
 * fallback de Pages sirvió como `index.html` 200 es un soft-404: la
 * devolvemos con el mismo shell (para que el cliente pinte Not Found) pero
 * con status 404. `/reports` es el alias cliente hacia Participación;
 * `/reportes` y `/sugerencias` además redirigen 301 en `_redirects`.
 */
const SPA_ROUTES = new Set([
  '/',
  '/index.html',
  '/login',
  '/privacidad',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
  '/mapa',
  '/participacion',
  '/reportes',
  '/sugerencias',
  '/reports',
  '/auth/callback',
  '/dashboard',
  '/perfil',
  '/admin',
  '/admin/images',
  '/admin/participacion',
  '/admin/reports',
  '/admin/sugerencias',
  '/admin/tramites',
  '/admin/reuniones',
  '/admin/padron',
  '/admin/finanzas',
  '/admin/dem-pipeline',
  '/admin/conocimiento',
  '/admin/canales',
]);

export function normalizePathname(pathname) {
  let path = pathname || '/';
  try {
    path = decodeURIComponent(path);
  } catch {
    // Un escape roto se compara tal cual.
  }
  if (path.length > 1 && path.endsWith('/')) path = path.slice(0, -1);
  return path;
}

export function isKnownSpaPath(pathname) {
  return SPA_ROUTES.has(normalizePathname(pathname));
}

export function shouldServeRouteNotFound(pathname, status, contentType) {
  if (isStaticAssetPath(pathname)) return false;
  if (status !== 200) return false;
  const type = (contentType || '').toLowerCase();
  if (!type.includes('text/html')) return false;
  return !isKnownSpaPath(pathname);
}

export function htmlNotFound(response) {
  const headers = new Headers(response.headers);
  headers.set('cache-control', 'no-store');
  headers.set('x-robots-tag', 'noindex');
  return new Response(response.body, {
    status: 404,
    statusText: 'Not Found',
    headers,
  });
}

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    const response = await env.ASSETS.fetch(request);
    const contentType = response.headers.get('content-type');
    if (shouldReplaceWithPlain404(pathname, response.status, contentType)) {
      return plainNotFound();
    }
    if (shouldServeRouteNotFound(pathname, response.status, contentType)) {
      return htmlNotFound(response);
    }
    return response;
  },
};
