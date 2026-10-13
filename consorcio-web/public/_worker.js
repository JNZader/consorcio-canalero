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

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    const response = await env.ASSETS.fetch(request);
    if (
      !shouldReplaceWithPlain404(pathname, response.status, response.headers.get('content-type'))
    ) {
      return response;
    }
    return plainNotFound();
  },
};
