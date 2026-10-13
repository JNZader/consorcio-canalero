import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { shouldReplaceWithPlain404 } from '../../public/_worker.js';

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

  it('ships the plain-404 worker inside the Pages build output', () => {
    const worker = readFileSync(join(process.cwd(), 'public/_worker.js'), 'utf8');
    expect(worker).toMatch(/export default/);
    expect(worker).toMatch(/env\.ASSETS\.fetch/);
    expect(worker).toMatch(/shouldReplaceWithPlain404/);
  });

  it('registers a one-shot vite:preloadError reload in main.tsx', () => {
    const main = readFileSync(join(process.cwd(), 'src/main.tsx'), 'utf8');
    expect(main).toMatch(/vite:preloadError/);
    expect(main).toMatch(/reloadOnceForStaleChunk/);
  });
});
