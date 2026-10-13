import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

describe('Cloudflare Pages redirects (FE-01)', () => {
  it('404s missing /assets/* before the SPA fallback', () => {
    const redirects = readFileSync(join(process.cwd(), 'public/_redirects'), 'utf8');
    const assetIdx = redirects.indexOf('/assets/* /404.html 404');
    const spaIdx = redirects.indexOf('/* /index.html 200');
    expect(assetIdx).toBeGreaterThan(-1);
    expect(spaIdx).toBeGreaterThan(assetIdx);
  });

  it('registers a one-shot vite:preloadError reload in main.tsx', () => {
    const main = readFileSync(join(process.cwd(), 'src/main.tsx'), 'utf8');
    expect(main).toMatch(/vite:preloadError/);
    expect(main).toMatch(/reloadOnceForStaleChunk/);
  });
});
