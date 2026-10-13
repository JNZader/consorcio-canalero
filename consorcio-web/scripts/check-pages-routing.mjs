/**
 * Comprueba el contrato de ruteo de Cloudflare Pages:
 *   - las rutas de la SPA responden 200 con el shell (recarga y deep link);
 *   - un asset que no existe responde 404 y el cuerpo no es HTML (FE-01).
 *
 * Uso:
 *   node scripts/check-pages-routing.mjs              # wrangler pages dev ./dist
 *   node scripts/check-pages-routing.mjs --fixture    # sitio minimo + public/
 *   node scripts/check-pages-routing.mjs --url URL    # preview o produccion
 *
 * `--fixture` y el modo dist arrancan `wrangler pages dev` (WRANGLER_BIN o
 * node_modules/.bin/wrangler). `--url` solo hace fetch.
 */

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const SPA_PATHS = ['/', '/mapa', '/participacion', '/admin', '/admin/images', '/login', '/perfil'];

const MISSING_ASSETS = [
  '/assets/this-chunk-does-not-exist.js',
  '/assets/this-chunk-does-not-exist.css',
  '/assets/this-font-does-not-exist.woff2',
  '/workbox-this-build-does-not-exist.js',
  '/sitemap.xml',
];

function parseArgs(argv) {
  const out = { url: '', dir: '', fixture: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--fixture') out.fixture = true;
    else if (arg === '--url') out.url = argv[++i] || '';
    else if (arg === '--dir') out.dir = argv[++i] || '';
    else throw new Error(`Argumento desconocido: ${arg}`);
  }
  if (out.url && (out.fixture || out.dir)) {
    throw new Error('--url no se combina con --fixture ni --dir');
  }
  return out;
}

function header(response, name) {
  return response.headers.get(name) || '';
}

async function fetchManual(url) {
  const response = await fetch(url, { redirect: 'manual' });
  const body = await response.text();
  return { response, body };
}

function assertSpa(path, { response, body }) {
  const type = header(response, 'content-type');
  if (response.status !== 200) {
    throw new Error(`${path} deberia ser 200 y fue ${response.status} (${type})`);
  }
  if (!type.toLowerCase().includes('text/html')) {
    throw new Error(`${path} deberia ser HTML y fue ${type}`);
  }
  if (!body.includes('id="root"')) {
    throw new Error(`${path} no sirvio el shell de la SPA`);
  }
  const frame = header(response, 'x-frame-options');
  if (frame.toUpperCase() !== 'DENY') {
    throw new Error(`${path} perdio X-Frame-Options (fue ${frame || '<vacio>'})`);
  }
}

function assertPlain404(path, { response, body }) {
  const type = header(response, 'content-type').toLowerCase();
  if (response.status !== 404) {
    throw new Error(`${path} deberia ser 404 y fue ${response.status} (${type})`);
  }
  if (type.includes('text/html') || type.includes('application/xhtml')) {
    throw new Error(`${path} respondio 404 con HTML (${type})`);
  }
  if (!type.includes('text/plain')) {
    throw new Error(`${path} deberia ser text/plain y fue ${type || '<vacio>'}`);
  }
  const trimmed = body.trim().toLowerCase();
  if (trimmed.startsWith('<!doctype') || trimmed.startsWith('<html') || body.includes('id="root"')) {
    throw new Error(`${path} devolvio un documento HTML en el 404`);
  }
  const cache = header(response, 'cache-control').toLowerCase();
  if (cache.includes('immutable') || cache.includes('max-age=31536000')) {
    throw new Error(`${path} cachea el 404 como asset inmutable (${cache})`);
  }
}

async function check(base) {
  const origin = base.replace(/\/$/, '');
  const failures = [];

  async function run(label, fn) {
    try {
      await fn();
      console.log(`ok  ${label}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failures.push(message);
      console.error(`FAIL ${message}`);
    }
  }

  for (const path of SPA_PATHS) {
    await run(`SPA ${path}`, async () => {
      assertSpa(path, await fetchManual(`${origin}${path}`));
    });
  }

  await run('SPA /participacion?tab=sugerencias', async () => {
    assertSpa('/participacion?tab=sugerencias', await fetchManual(
      `${origin}/participacion?tab=sugerencias`,
    ));
  });

  for (const path of MISSING_ASSETS) {
    await run(`404 ${path}`, async () => {
      assertPlain404(path, await fetchManual(`${origin}${path}`));
    });
  }

  await run('robots.txt', async () => {
    const file = await fetchManual(`${origin}/robots.txt`);
    const type = header(file.response, 'content-type').toLowerCase();
    if (file.response.status !== 200 || !type.includes('text/plain')) {
      throw new Error(`/robots.txt deberia ser 200 text/plain y fue ${file.response.status} ${type}`);
    }
    if (file.body.includes('id="root"')) throw new Error('/robots.txt sirvio el shell de la SPA');
  });

  await run('version.json', async () => {
    const file = await fetchManual(`${origin}/version.json`);
    const type = header(file.response, 'content-type').toLowerCase();
    if (file.response.status !== 200 || !type.includes('json')) {
      throw new Error(`/version.json deberia ser 200 json y fue ${file.response.status} ${type}`);
    }
  });

  await run('asset real', async () => {
    const home = await fetchManual(`${origin}/`);
    assertSpa('/', home);
    const match = home.body.match(/\/assets\/[^"' ]+\.js/);
    const assetPath = match ? match[0] : '/assets/real.js';
    const asset = await fetchManual(`${origin}${assetPath}`);
    const type = header(asset.response, 'content-type').toLowerCase();
    if (asset.response.status !== 200) {
      throw new Error(`${assetPath} deberia ser 200 y fue ${asset.response.status}`);
    }
    if (!type.includes('javascript')) {
      throw new Error(`${assetPath} deberia ser javascript y fue ${type}`);
    }
    const cache = header(asset.response, 'cache-control').toLowerCase();
    if (!cache.includes('immutable')) {
      throw new Error(`${assetPath} perdio el cache inmutable (${cache || '<vacio>'})`);
    }
    if (asset.body.includes('id="root"') || asset.body.trim().startsWith('<!doctype')) {
      throw new Error(`${assetPath} sirvio HTML en vez del modulo`);
    }
  });

  await run('301 /reportes', async () => {
    const { response } = await fetchManual(`${origin}/reportes`);
    if (response.status !== 301) {
      throw new Error(`/reportes deberia ser 301 y fue ${response.status}`);
    }
    const location = header(response, 'location');
    if (!location.endsWith('/participacion')) {
      throw new Error(`/reportes redirige a ${location || '<vacio>'}`);
    }
  });

  await run('301 /sugerencias', async () => {
    const { response } = await fetchManual(`${origin}/sugerencias`);
    if (response.status !== 301) {
      throw new Error(`/sugerencias deberia ser 301 y fue ${response.status}`);
    }
    const location = header(response, 'location');
    if (!location.includes('/participacion?tab=sugerencias')) {
      throw new Error(`/sugerencias redirige a ${location || '<vacio>'}`);
    }
  });

  await run('308 /index.html', async () => {
    const { response, body } = await fetchManual(`${origin}/index.html`);
    if (response.status === 200 && body.includes('id="root"')) return;
    if (response.status !== 308) {
      throw new Error(`/index.html deberia ser 308 hacia / y fue ${response.status}`);
    }
    const location = header(response, 'location');
    let pathname = location;
    try {
      pathname = new URL(location, origin).pathname;
    } catch {
      pathname = location;
    }
    if (pathname !== '/') {
      throw new Error(`/index.html redirige a ${location || '<vacio>'}`);
    }
  });

  if (failures.length) {
    throw new Error(`${failures.length} comprobacion(es) fallaron`);
  }
}

function writeFixture() {
  const dir = mkdtempSync(join(tmpdir(), 'pages-routing-'));
  mkdirSync(join(dir, 'assets'), { recursive: true });
  mkdirSync(join(dir, 'data'), { recursive: true });
  writeFileSync(
    join(dir, 'index.html'),
    '<!doctype html><html><head><title>APP</title></head><body><div id="root"></div><script type="module" src="/assets/real.js"></script></body></html>\n',
  );
  writeFileSync(join(dir, 'assets', 'real.js'), 'console.log("real-chunk")\n');
  writeFileSync(join(dir, 'data', 'ok.json'), '{}\n');
  writeFileSync(join(dir, 'robots.txt'), 'ok\n');
  writeFileSync(join(dir, 'version.json'), '{"sha":"fixture"}\n');
  writeFileSync(join(dir, '_redirects'), readFileSync(join(root, 'public/_redirects')));
  writeFileSync(join(dir, '_headers'), readFileSync(join(root, 'public/_headers')));
  writeFileSync(join(dir, '_worker.js'), readFileSync(join(root, 'public/_worker.js')));
  // Si alguien vuelve a commitear public/404.html, el fixture lo incluye
  // y las rutas profundas tienen que fallar esta prueba.
  try {
    writeFileSync(join(dir, '404.html'), readFileSync(join(root, 'public/404.html')));
  } catch {
    // ausencia esperada
  }
  return dir;
}

function wranglerBin() {
  if (process.env.WRANGLER_BIN) return process.env.WRANGLER_BIN;
  return join(root, 'node_modules', '.bin', 'wrangler');
}

async function portReady(port) {
  for (let i = 0; i < 80; i += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/`, { redirect: 'manual' });
      await response.arrayBuffer();
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
  }
  throw new Error(`wrangler no abrio el puerto ${port}`);
}

async function withWrangler(dir, fn) {
  const bin = wranglerBin();
  const port = 8900 + Math.floor(Math.random() * 500);
  const child = spawn(
    bin,
    [
      'pages',
      'dev',
      dir,
      '--port',
      String(port),
      '--ip',
      '127.0.0.1',
      '--log-level',
      'error',
      '--show-interactive-dev-session=false',
      '--persist-to',
      join(tmpdir(), 'pages-routing-wrangler'),
    ],
    {
      cwd: root,
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );
  let logs = '';
  child.stdout?.on('data', (chunk) => {
    logs += chunk.toString();
  });
  child.stderr?.on('data', (chunk) => {
    logs += chunk.toString();
  });
  try {
    await portReady(port);
    await fn(`http://127.0.0.1:${port}`);
  } catch (error) {
    if (logs.trim()) console.error(logs.trim());
    throw error;
  } finally {
    if (child.pid) {
      try {
        process.kill(-child.pid, 'SIGTERM');
      } catch {
        child.kill('SIGTERM');
      }
    }
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.url) {
    await check(args.url);
    return;
  }
  const fixture = args.fixture;
  const dir = fixture ? writeFixture() : args.dir || join(root, 'dist');
  try {
    await withWrangler(dir, (base) => check(base));
  } finally {
    if (fixture) rmSync(dir, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
