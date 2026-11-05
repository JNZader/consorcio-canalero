import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  isKnownSpaPath,
  shouldReplaceWithPlain404,
  shouldServeRouteNotFound,
} from '../../public/_worker.js';

describe('Cloudflare Pages routing (SPA + FE-01)', () => {
  it('does not ship a root 404.html (that disables the Pages SPA fallback)', () => {
    expect(existsSync(join(process.cwd(), 'public/404.html'))).toBe(false);
  });

  it('keeps retired public URLs on 301 and does not splat to index.html', () => {
    const redirects = readFileSync(join(process.cwd(), 'public/_redirects'), 'utf8');
    const rules = redirects
      .split('\n')
      .filter((line) => {
        const trimmed = line.trim();
        return trimmed.length > 0 && !trimmed.startsWith('#');
      })
      .join('\n');
    expect(rules).toMatch(/^\/reportes \/participacion 301/m);
    expect(rules).toMatch(/^\/sugerencias \/participacion\?tab=sugerencias 301/m);
    expect(rules).not.toMatch(/\/index\.html\s+200/);
    expect(rules).not.toMatch(/^\s*\/\*\s+\/\s+200/m);
    expect(rules).not.toContain('404.html');
    const reportes = rules.indexOf('/reportes ');
    const splat = rules.search(/^\s*\/\*/m);
    if (splat !== -1) expect(reportes).toBeLessThan(splat);
  });

  it('turns a missing static asset into a plain 404 and leaves SPA routes alone', () => {
    expect(shouldReplaceWithPlain404('/mapa', 200, 'text/html; charset=utf-8')).toBe(false);
    expect(shouldReplaceWithPlain404('/admin/images', 200, 'text/html')).toBe(false);
    expect(shouldReplaceWithPlain404('/index.html', 308, '')).toBe(false);
    expect(shouldReplaceWithPlain404('/assets/missing.js', 200, 'text/html; charset=utf-8')).toBe(
      true
    );
    expect(shouldReplaceWithPlain404('/assets/missing.css', 404, 'text/html')).toBe(true);
    expect(shouldReplaceWithPlain404('/assets/missing.woff2', 200, 'text/html')).toBe(true);
    expect(shouldReplaceWithPlain404('/workbox-stale.js', 200, 'text/html')).toBe(true);
    expect(shouldReplaceWithPlain404('/this-file-does-not-exist.xml', 200, 'text/html')).toBe(true);
    expect(shouldReplaceWithPlain404('/sitemap.xml', 200, 'application/xml')).toBe(false);
    expect(shouldReplaceWithPlain404('/assets/real.js', 200, 'application/javascript')).toBe(false);
    expect(shouldReplaceWithPlain404('/assets/real.css', 200, 'text/css')).toBe(false);
    expect(shouldReplaceWithPlain404('/data/ok.geojson', 200, 'application/geo+json')).toBe(false);
    expect(shouldReplaceWithPlain404('/robots.txt', 200, 'text/plain; charset=utf-8')).toBe(false);
    expect(shouldReplaceWithPlain404('/version.json', 200, 'application/json')).toBe(false);
  });

  it('turns an unknown HTML route into a real 404 and keeps the SPA routes', () => {
    expect(shouldServeRouteNotFound('/esta-ruta-no-existe', 200, 'text/html')).toBe(true);
    expect(shouldServeRouteNotFound('/admin/no-existe', 200, 'text/html; charset=utf-8')).toBe(
      true
    );
    expect(shouldServeRouteNotFound('/mapa/', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/reports', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/reportes', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/sugerencias', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/admin/reports', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/admin/sugerencias', 200, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/mapa', 404, 'text/html')).toBe(false);
    expect(shouldServeRouteNotFound('/assets/missing.js', 200, 'text/html')).toBe(false);
    expect(isKnownSpaPath('/participacion')).toBe(true);
    expect(isKnownSpaPath('/no-existe')).toBe(false);
  });

  it('ships the plain-404 worker inside the Pages build output', () => {
    const worker = readFileSync(join(process.cwd(), 'public/_worker.js'), 'utf8');
    expect(worker).toMatch(/export default/);
    expect(worker).toMatch(/env\.ASSETS\.fetch/);
    expect(worker).toMatch(/shouldReplaceWithPlain404/);
    expect(worker).toMatch(/shouldServeRouteNotFound/);
  });

  it('keeps SPA_ROUTES in lockstep with the router', () => {
    const routeTree = readFileSync(join(process.cwd(), 'src/routeTree.gen.tsx'), 'utf8');
    const worker = readFileSync(join(process.cwd(), 'public/_worker.js'), 'utf8');
    const routeBlock = worker.split('const SPA_ROUTES = new Set([')[1]?.split(']);')[0] ?? '';
    const declared = new Set([...routeBlock.matchAll(/'([^']*)'/g)].map((match) => match[1]));
    const blocks = [
      ...routeTree.matchAll(/const (\w+) = createRoute\(\{([\s\S]*?)\n\}\);/g),
    ];
    const routes = new Map<string, { parent: string; path: string }>();
    for (const match of blocks) {
      const parent = match[2].match(/getParentRoute: \(\) => (\w+)/)?.[1];
      const path = match[2].match(/\n\s+path: '([^']*)'/)?.[1];
      if (parent && path !== undefined) routes.set(match[1], { parent, path });
    }
    const full = new Map<string, string>();
    const resolve = (name: string): string => {
      const cached = full.get(name);
      if (cached !== undefined) return cached;
      const route = routes.get(name);
      if (!route) return '';
      const parentPath = route.parent === 'rootRouteWithComponent' ? '' : resolve(route.parent);
      const joined =
        route.path === '/'
          ? parentPath || '/'
          : `${parentPath}${route.path.startsWith('/') ? route.path : `/${route.path}`}`;
      full.set(name, joined);
      return joined;
    };
    const fromRouter = new Set([...routes.keys()].map(resolve));
    for (const path of fromRouter) {
      expect(declared.has(path), path).toBe(true);
    }
    const extras = [...declared].filter((path) => path !== '/index.html' && !fromRouter.has(path));
    expect(extras).toEqual([]);
  });

  it('registers a one-shot vite:preloadError reload in main.tsx', () => {
    const main = readFileSync(join(process.cwd(), 'src/main.tsx'), 'utf8');
    expect(main).toMatch(/vite:preloadError/);
    expect(main).toMatch(/reloadOnceForStaleChunk/);
  });
});
