import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

function cspLine(): string {
  const headers = readFileSync(join(process.cwd(), 'public/_headers'), 'utf8');
  const line = headers.split('\n').find((row) => row.trim().startsWith('Content-Security-Policy:'));
  if (!line) throw new Error('CSP header missing');
  return line;
}

describe('Cloudflare Pages security headers', () => {
  it('allows backend raster tiles in img-src for DEM and 3D map layers', () => {
    const line = cspLine();
    expect(line).toContain('img-src');
    expect(line).toContain('https://cc10demayo-api.javierzader.com');
    expect(line).toContain('https://cc10demayo-tiles.javierzader.com');
  });

  it('allows MapLibre glyph PBFs in connect-src so road labels paint in production', () => {
    const line = cspLine();
    expect(line).toContain('connect-src');
    expect(line).toContain('https://tiles.openfreemap.org');
    expect(line).toContain('https://server.arcgisonline.com');
    expect(line).not.toContain('https://basemaps.cartocdn.com');
    expect(line).not.toContain('https://demotiles.maplibre.org');
  });

  it('lists exact pages.dev and javierzader.com hosts (SEC-02)', () => {
    const line = cspLine();
    expect(line).toContain('https://consorcio-canalero.pages.dev');
    expect(line).not.toContain('https://*.pages.dev');
    expect(line).not.toContain('https://*.javierzader.com');
    expect(line).not.toMatch(/https:\/\/\*\.[a-z0-9-]*pages\.dev/);
  });

  it('drops the unanswered consorcio10demayo.com.ar origin (SEC-05)', () => {
    expect(cspLine()).not.toContain('consorcio10demayo.com.ar');
  });

  it('allows the Sentry and Better Stack endpoints the browser shippers use (OBS-01)', () => {
    const line = cspLine();
    // Runbook DSN: https://<key>@<org>.ingest.us.sentry.io/<project>
    expect(line).toContain('https://*.ingest.us.sentry.io');
    // @logtail/core default, and the EU override documented in lib/logtail.ts
    expect(line).toContain('https://in.logs.betterstack.com');
    expect(line).toContain('https://eu1.logs.betterstack.com');
  });
});
