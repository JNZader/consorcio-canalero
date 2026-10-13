/**
 * Cloudflare Pages: sin un `404.html` en la raíz el sitio es una SPA y
 * cualquier ruta que no sea un archivo estático recibe `index.html` con 200.
 * Eso también le pasa a un chunk viejo (`/assets/index-HASH.js`) después de
 * un deploy: el navegador recibe HTML, el módulo no evalúa y la pantalla
 * queda en blanco (FE-01).
 *
 * Este middleware corre después del asset pipeline (`context.next()`). Si la
 * URL parece un archivo estático y la respuesta es el shell HTML (200) o un
 * 404 HTML de plataforma, la reemplaza por un 404 `text/plain`. Las rutas de
 * la SPA (sin extensión) se dejan pasar.
 *
 * No hay `/* /index.html 200` en `_redirects`: ese destino choca con el 308
 * de pretty URLs (`/index.html` → `/`) y, junto con un `404.html` de raíz,
 * hace que `/mapa` y el resto de las rutas profundas respondan 404.
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

export async function onRequest(context) {
  const { pathname } = new URL(context.request.url);
  const response = await context.next();
  if (
    !shouldReplaceWithPlain404(pathname, response.status, response.headers.get('content-type'))
  ) {
    return response;
  }
  return plainNotFound();
}
